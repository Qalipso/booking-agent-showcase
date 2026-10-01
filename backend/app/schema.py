"""Единая схема конфигурации.

Источник правды — config/schema.json. По ней строится админ-форма, работает
валидация PUT и генерируется .env для деплоя.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
SCHEMA_FILE = CONFIG_DIR / "schema.json"

SCHEMA: dict[str, Any] = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))

WEEKDAY_VALUES = {0, 1, 2, 3, 4, 5, 6}
MASK = "••••••••"
SECRET_KEYS = {
    "clientSecret", "refreshToken", "apiKey", "url", "supabaseServiceKey",
    "whatsappToken", "whatsappVerifyToken", "telegramBotToken",
}

SALON_SECTION_IDS = {"salon", "services", "masters"}
INTEGRATION_SECTIONS = [s for s in SCHEMA["sections"] if s["file"] == "integration.json"]


# --- работа с путями вида "workHours.start" ---------------------------------

def get(obj: Any, path: str, default: Any = None) -> Any:
    cur = obj
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def put(obj: dict, path: str, value: Any) -> None:
    keys = path.split(".")
    for key in keys[:-1]:
        obj = obj.setdefault(key, {})
    obj[keys[-1]] = value


def _visible(field: dict, scope: dict) -> bool:
    cond = field.get("showIf")
    if not cond:
        return True
    for key, expected in cond.items():
        actual = get(scope, key)
        if isinstance(expected, bool):
            if bool(actual) != expected:
                return False
        elif actual != expected:
            return False
    return True


def _minutes(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def _check_field(field: dict, value: Any, errors: list[str], where: str) -> None:
    label = f"{where}{field['label']}"
    ftype = field.get("type", "text")
    if ftype in ("bool", "hidden"):  # служебные поля формой не заполняются
        return

    empty = value is None or value == "" or (isinstance(value, list) and not value)
    if field.get("required") and empty:
        errors.append(f"{label}: обязательное поле")
        return
    if empty:
        return
    if ftype == "secret" and value == MASK:  # секрет не менялся
        return

    if ftype == "number":
        try:
            n = float(value)
        except (TypeError, ValueError):
            errors.append(f"{label}: нужно число")
            return
        if field.get("min") is not None and n < field["min"]:
            errors.append(f"{label}: минимум {field['min']}")
        elif field.get("max") is not None and n > field["max"]:
            errors.append(f"{label}: максимум {field['max']}")
    elif ftype == "time":
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(value)):
            errors.append(f"{label}: формат ЧЧ:ММ")
    elif ftype == "slug":
        if not re.fullmatch(r"[a-z0-9_-]{2,32}", str(value)):
            errors.append(f"{label}: латиница, цифры, дефис (2–32)")
    elif ftype == "url":
        if not str(value).startswith(("http://", "https://")):
            errors.append(f"{label}: ссылка должна начинаться с http(s)://")
    elif ftype == "weekdays":
        if not isinstance(value, list) or any(int(d) not in WEEKDAY_VALUES for d in value):
            errors.append(f"{label}: некорректные дни недели")
    elif ftype == "select":
        allowed = [o if isinstance(o, str) else o["value"] for o in field["options"]]
        if value not in allowed:
            errors.append(f"{label}: недопустимое значение")


def validate_config(data: dict) -> list[str]:
    """Полная проверка конфигурации. Пустой список = всё в порядке."""
    errors: list[str] = []

    for section in SCHEMA["sections"]:
        if section["kind"] == "object":
            scope = data.get(section["id"]) or {}
            for field in section["fields"]:
                if _visible(field, scope):
                    _check_field(field, get(scope, field["key"]), errors, f"{section['title']} → ")
        else:
            items = data.get(section["id"]) or []
            if not items and section.get("required", True):
                errors.append(f"{section['title']}: нужна хотя бы одна запись")
            for i, item in enumerate(items, 1):
                where = f"{section['title']} #{i} → "
                for field in section["fields"]:
                    if _visible(field, item):
                        _check_field(field, get(item, field["key"]), errors, where)
            ids = [it.get(section["idField"]) for it in items]
            if len(set(ids)) != len(ids):
                errors.append(f"{section['title']}: коды должны быть уникальны")

    # Кросс-полевые правила.
    salon = data.get("salon") or {}
    start, end = get(salon, "workHours.start"), get(salon, "workHours.end")
    if start and end and start >= end:
        errors.append("Салон → закрытие должно быть позже открытия")

    services = data.get("services") or []
    masters = data.get("masters") or []
    day_minutes = _minutes(end) - _minutes(start) if start and end else 10**6
    for svc in services:
        try:
            duration = int(svc.get("duration") or 0)
        except (TypeError, ValueError):
            continue
        if duration > day_minutes:
            errors.append(
                f"Услуги → «{svc.get('title') or svc.get('id')}» длиннее рабочего дня — слотов не будет"
            )

    service_ids = {s.get("id") for s in services}
    salon_days = [int(d) for d in (salon.get("workDays") or [])]
    for m in masters:
        for sid in m.get("services") or []:
            if sid not in service_ids:
                errors.append(f"Мастера → {m.get('name') or m.get('id')}: неизвестная услуга «{sid}»")
        if salon_days and any(int(d) not in salon_days for d in m.get("workDays") or []):
            errors.append(f"Мастера → {m.get('name') or m.get('id')}: рабочий день вне графика салона")

        # Смена мастера: пустое поле — «как у салона», поэтому проверяем только
        # заполненное. Без этой проверки смена за пределами часов салона просто
        # не даёт слотов, и владелец ищет причину в календаре, а не в форме.
        #
        # Адресуем ошибку графику мастеров, а не карточке: часы смены форма
        # больше не показывает, и «исправьте в Мастерах» отправляло бы искать
        # поле, которого там нет.
        who = m.get("name") or m.get("id")
        m_start, m_end = (get(m, "workHours.start") or ""), (get(m, "workHours.end") or "")
        if m_start and m_end and m_start >= m_end:
            errors.append(f"График мастеров → {who}: конец смены должен быть позже начала")
        if start and m_start and m_start < start:
            errors.append(f"График мастеров → {who}: смена начинается раньше открытия салона ({start})")
        if end and m_end and m_end > end:
            errors.append(f"График мастеров → {who}: смена заканчивается позже закрытия салона ({end})")

    integration = data.get("integration") or {}
    if integration.get("mode") == "service_account" and not integration.get("serviceAccountFile"):
        errors.append("Google Calendar → укажите путь к JSON-ключу")
    # Незаконченного подключения Google форма больше не считает ошибкой. Правило
    # «для OAuth нужен refresh token» запирало панель наглухо: токен выдаётся
    # только после входа в Google, а войти было нельзя — форма не сохранялась,
    # и введённые Client ID с Secret не доживали до кнопки входа. Состояние
    # подключения показывает карточка, а не блокировка сохранения всей
    # конфигурации, включая разделы, к Google отношения не имеющие.

    # Состояние подключений форма больше не проверяет — ни Google, ни AI. Эти
    # правила запирали сохранение всей панели ради того, что в форме уже не
    # вводится: ключ проверяется у провайдера в момент подключения, а рассинхрон
    # («включено, ключа нет») бота не ломает — он просто ведёт кнопочный
    # сценарий. Блокировать из-за этого правку часов работы незачем.

    # Хранилище в форме не настраивается: база одна на весь сервис, её адрес
    # приходит из DATABASE_URL. Настроить доступ к базе через форму, которая
    # сама хранится в этой базе, невозможно — раздел «База данных» только
    # показывает состояние.

    channel = data.get("channel") or {}
    if channel.get("kind") == "whatsapp" and not all(
        channel.get(k) for k in ("whatsappPhoneId", "whatsappToken", "whatsappVerifyToken")
    ):
        errors.append("Канал → для WhatsApp нужны Phone number ID, access token и verify token")

    policies = data.get("policies") or {}
    if policies.get("allowCancel") is False and policies.get("allowReschedule") is True:
        errors.append("Правила → перенос без права отмены невозможен")

    # Уведомления разделены на два экрана формы, но остаются одной секцией
    # файла: правила проверяем по объединённому срезу, иначе «Telegram выбран,
    # но чат не привязан» перестало бы срабатывать — провайдер уехал на соседний
    # экран, а флаг «включено» остался на этом.
    notifications = {**(data.get("notifications") or {}),
                     **(data.get("notificationsInternal") or {}),
                     **(data.get("notificationsTwilio") or {})}
    if notifications.get("enabled"):
        if notifications.get("provider") == "twilio" and not notifications.get("twilioWhatsappFrom") \
                and notifications.get("clientChannel") == "whatsapp":
            errors.append("Уведомления → укажите WhatsApp-номер Twilio")
        if notifications.get("provider") == "twilio" and notifications.get("smsFallback") \
                and not notifications.get("twilioSmsFrom"):
            errors.append("Уведомления → для SMS-резерва нужен SMS-номер Twilio")
        if notifications.get("ownerProvider") == "twilio" and not notifications.get("ownerPhone"):
            errors.append("Уведомления → укажите телефон владельца")
        if notifications.get("ownerProvider") == "email":
            handoff = data.get("handoff") or {}
            if not str(handoff.get("adminEmail") or "").strip():
                errors.append("Уведомления → для Email укажите email администратора")
            if not str(notifications.get("smtpHost") or "").strip() \
                    or not str(notifications.get("smtpFrom") or "").strip():
                errors.append("Уведомления → для Email укажите SMTP host и адрес отправителя")
            if notifications.get("smtpUsername") and not notifications.get("smtpPassword"):
                errors.append("Уведомления → для SMTP пользователя нужен пароль")
        # Половина подключения — молчащий канал: провайдер telegram с пустым chatId
        # даёт «Не указан получатель» на каждой записи, и владелец узнаёт об этом
        # только из лога. Ошибка формы escapable: чат привязывается кнопкой мимо
        # валидации, а сам провайдер меняется в этом же селекте.
        if notifications.get("ownerProvider") == "telegram" \
                and not str((data.get("handoff") or {}).get("telegramChatId") or "").strip():
            errors.append("Уведомления → Telegram выбран, но чат не привязан: "
                          "«Передача администратору» → «Связать чат»")
        hours = notifications.get("sameDayHours")
        if hours not in (None, "") and float(hours) <= 0:
            errors.append("Уведомления → напоминание в день визита должно быть за положительное число часов")

    return errors


def secret_path(section: dict, field: dict) -> str:
    """Полный путь секрета: `ai.apiKey`, `handoff.telegramBotToken`."""
    return f"{section['path']}.{field['key']}" if section.get("path") else field["key"]


def is_secret(section: dict, field: dict) -> bool:
    """Секрет — по типу поля или по списку известных путей.

    ``refreshToken`` объявлен скрытым, а не секретным (форма его не показывает),
    но в файл он тоже попадать не должен — приходит из OAuth-колбэка.
    """
    from .secretstore import SECRET_PATHS

    return field.get("type") == "secret" or secret_path(section, field) in SECRET_PATHS


_MISSING = object()


def _normalise_form_value(field: dict, value: Any) -> Any:
    """Привести значение формы к формату salon.json по описанию поля."""
    ftype = field.get("type", "text")
    if value is _MISSING or value is None:
        if "default" in field:
            value = field["default"]
        elif ftype in ("weekdays", "serviceRefs"):
            value = []
        elif ftype == "number":
            value = 0
        else:
            value = ""
    elif value == "" and "default" in field:
        value = field["default"]

    if ftype == "number":
        return int(value or 0)
    if ftype == "weekdays":
        return sorted(int(d) for d in value or [])
    if ftype == "serviceRefs":
        return [str(item) for item in value or []]
    if ftype == "bool":
        return bool(value)
    return value


def _list_section_to_file(section: dict, items: list[dict],
                          previous_items: list[dict] | None = None) -> list[dict]:
    """Собрать список salon.json из схемы, без ручного перечня полей.

    Поля с ``managedOutsideForm`` изменяют отдельные endpoints, а не форма
    настроек. Для существующей записи файл поэтому авторитетнее даже старого,
    но формально валидного снимка формы.
    """
    id_field = section["idField"]
    previous_by_id = {
        item.get(id_field): item for item in (previous_items or [])
        if item.get(id_field) is not None
    }
    result: list[dict] = []
    for item in items:
        previous = previous_by_id.get(item.get(id_field), {})
        saved: dict[str, Any] = {}
        for field in section["fields"]:
            key = field["key"]
            value = get(previous, key, _MISSING) if field.get("managedOutsideForm") \
                else get(item, key, _MISSING)
            if value is _MISSING:
                value = get(item, key, _MISSING)
            put(saved, key, _normalise_form_value(field, value))
        result.append(saved)
    return result


def to_files(data: dict, previous_integration: dict | None = None,
             on_secret=None, previous_salon: dict | None = None) -> tuple[dict, dict]:
    """Форма → (salon.json, integration.json).

    Секреты в JSON не попадают вовсе: новое значение уходит в ``on_secret``
    (хранилище секретов), маска ``MASK`` означает «не менялось».
    """
    previous_integration = previous_integration or {}
    previous_salon = previous_salon or {}
    salon_section = next(s for s in SCHEMA["sections"] if s["id"] == "salon")

    salon: dict[str, Any] = {}
    src = data.get("salon") or {}
    for field in salon_section["fields"]:
        value = get(src, field["key"])
        if field["type"] == "number" and value not in (None, ""):
            value = int(value)
        if field["type"] == "weekdays":
            value = sorted(int(d) for d in value or [])
        put(salon, field["key"], value)

    for section in (s for s in SCHEMA["sections"]
                    if s.get("file") == "salon.json" and s.get("kind") == "list"):
        section_id = section["id"]
        salon[section_id] = _list_section_to_file(
            section,
            data.get(section_id) or [],
            previous_salon.get(section_id) or [],
        )

    integration: dict[str, Any] = {}
    for section in INTEGRATION_SECTIONS:
        section_src = data.get(section["id"]) or {}
        path = section.get("path")
        out: dict[str, Any] = {}
        for field in section["fields"]:
            value = get(section_src, field["key"])
            if is_secret(section, field):
                # Секрет уезжает в хранилище, а в файле не остаётся даже пустым.
                #
                # Пустая строка секрет НЕ затирает. Панель, открытая до
                # подключения, держит эти поля пустыми, и автосохранение
                # стирало только что сохранённые ключи: Twilio подключался, а
                # через несколько секунд сам себя терял. Убрать ключи можно
                # кнопкой «Отключить» — она и предупреждает о последствиях.
                if value not in (None, "", MASK) and on_secret:
                    on_secret(secret_path(section, field), str(value))
                continue
            if field["type"] == "number" and value not in (None, ""):
                value = int(value)
            if field["type"] == "bool":
                # Отсутствие ключа — не «выключено». Форма могла быть открыта до
                # того, как поле появилось в схеме, и тогда любое сохранение
                # тихо гасило умолчание: так «бот работает сам» превратился на
                # проде в false, и бот снова начал обещать звонок администратора.
                value = bool(field.get("default", False)) if value is None else bool(value)
            if value is not None:
                put(out, field["key"], value)
        if path:
            # Дополняем, а не заменяем: один раздел файла собирают несколько
            # секций формы. Уведомления разделены на внутренние и клиентские —
            # это два экрана, но по-прежнему одна секция `notifications`, и
            # присваивание здесь стирало бы поля соседнего экрана.
            integration.setdefault(path, {}).update(out)
        else:
            integration.update(out)

    return salon, integration


def to_form(salon: dict, integration: dict, has_secret=None) -> dict:
    """Файлы → форма.

    Секретов в файлах нет, поэтому наличие каждого спрашиваем у хранилища и
    показываем маску — само значение форме не отдаём никогда.
    """
    form: dict[str, Any] = {}
    salon_section = next(s for s in SCHEMA["sections"] if s["id"] == "salon")

    salon_fields: dict[str, Any] = {}
    for field in salon_section["fields"]:
        value = get(salon, field["key"])
        if value is None or value == "":
            value = field.get("default", "")
        put(salon_fields, field["key"], value)
    form["salon"] = salon_fields
    for section in (s for s in SCHEMA["sections"]
                    if s.get("file") == "salon.json" and s.get("kind") == "list"):
        # Копия, а не ссылка. Иначе форма и живой конфиг арендатора — один и
        # тот же объект: правка в памяти переписывает настройки, минуя
        # валидацию и запись на диск. Особенно это ломает поля с
        # `managedOutsideForm`, весь смысл которых в том, что при сохранении
        # формы побеждает файл, — сравнивать было бы не с чем, previous и item
        # оказывались бы одним словарём.
        form[section["id"]] = copy.deepcopy(salon.get(section["id"]) or [])

    for section in INTEGRATION_SECTIONS:
        path = section.get("path")
        src = (integration.get(path) or {}) if path else integration
        out: dict[str, Any] = {}
        for field in section["fields"]:
            value = get(src, field["key"])
            if is_secret(section, field):
                filled = has_secret(secret_path(section, field)) if has_secret else False
                value = MASK if filled else ""
            if value is None:
                value = field.get("default", False if field["type"] == "bool" else "")
            put(out, field["key"], value)
        form[section["id"]] = out
    return form


def to_env(integration: dict, slug: str = "") -> str:
    """Шпаргалка по переменным окружения для деплоя.

    Значения секретов сюда не попадают — только имена переменных, которые нужно
    задать на сервере (Coolify → Environment Variables). Это ровно тот файл,
    который раньше утекал в репозиторий вместе с токеном Telegram.
    """
    from .secretstore import SECRET_ENV, env_name

    lines = ["# Справка для деплоя. Секреты задаются в окружении сервера, не здесь."]

    def put_line(key: str, value: Any) -> None:
        if value is None or value == "":
            return
        if isinstance(value, bool):
            value = "true" if value else "false"
        lines.append(f"{key}={value}")

    put_line("GOOGLE_CALENDAR_MODE", integration.get("mode"))
    put_line("GOOGLE_SERVICE_ACCOUNT_FILE", integration.get("serviceAccountFile"))
    put_line("GOOGLE_IMPERSONATE_USER", integration.get("impersonateUser"))
    put_line("GOOGLE_CLIENT_ID", integration.get("clientId"))

    ai = integration.get("ai") or {}
    for env_key, key in [
        ("AI_ENABLED", "enabled"), ("AI_PROVIDER", "provider"), ("AI_MODEL", "model"),
        ("AI_MAX_STEPS", "maxSteps"), ("AI_TIMEOUT_SECONDS", "timeoutSeconds"),
        ("AI_LANGUAGE", "language"),
    ]:
        put_line(env_key, ai.get(key))

    channel = integration.get("channel") or {}
    put_line("CHANNEL", channel.get("kind"))
    put_line("ALLOWED_ORIGINS", channel.get("allowedOrigins"))
    put_line("WHATSAPP_PHONE_ID", channel.get("whatsappPhoneId"))

    policies = integration.get("policies") or {}
    for env_key, key in [
        ("REQUIRE_CONFIRMATION", "requireExplicitConfirmation"),
        ("RECHECK_SLOT", "recheckSlotBeforeInsert"),
        ("IDEMPOTENCY_ENABLED", "idempotencyEnabled"),
        ("ALLOW_CANCEL", "allowCancel"), ("ALLOW_RESCHEDULE", "allowReschedule"),
        ("MAX_BOOKINGS_PER_PHONE_PER_DAY", "maxBookingsPerPhonePerDay"),
        ("RATE_LIMIT_PER_MINUTE", "rateLimitPerMinute"),
        ("MASK_PII_IN_LOGS", "maskPiiInLogs"), ("DATA_RETENTION_DAYS", "dataRetentionDays"),
    ]:
        put_line(env_key, policies.get(key))

    handoff = integration.get("handoff") or {}
    for env_key, key in [
        ("ADMIN_NAME", "adminName"), ("ADMIN_WHATSAPP", "adminWhatsapp"),
        ("ADMIN_EMAIL", "adminEmail"), ("TELEGRAM_CHAT_ID", "telegramChatId"),
    ]:
        put_line(env_key, handoff.get(key))

    notifications = integration.get("notifications") or {}
    for env_key, key in [
        ("NOTIFY_ENABLED", "enabled"), ("NOTIFY_PROVIDER", "provider"),
        ("NOTIFY_CLIENT_CHANNEL", "clientChannel"), ("NOTIFY_OWNER_PROVIDER", "ownerProvider"),
        ("NOTIFY_DAY_BEFORE_AT", "dayBeforeAt"), ("NOTIFY_SAME_DAY_HOURS", "sameDayHours"),
        ("TWILIO_WHATSAPP_FROM", "twilioWhatsappFrom"), ("TWILIO_SMS_FROM", "twilioSmsFrom"),
        ("SMTP_HOST", "smtpHost"), ("SMTP_PORT", "smtpPort"),
        ("SMTP_SECURITY", "smtpSecurity"), ("SMTP_USERNAME", "smtpUsername"),
        ("SMTP_FROM", "smtpFrom"),
    ]:
        put_line(env_key, notifications.get(key))

    lines.append("")
    lines.append("# Секреты — задать в окружении сервера (значения здесь не показываются):")
    lines.append("DATABASE_URL=...")
    lines.append("ADMIN_TOKEN=...")
    for path in sorted(SECRET_ENV):
        lines.append(f"# {path} → {SECRET_ENV[path]}"
                     + (f" или {env_name(path, slug)}" if slug else ""))

    return "\n".join(lines) + "\n"
