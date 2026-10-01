"""Планирование и отправка уведомлений.

AI-агент не «помнит», когда писать клиенту. После подтверждения записи backend
ставит именованные задачи в таблицу ``notifications``, а в момент отправки
обработчик заново сверяется с базой: запись всё ещё подтверждена, время не
менялось, сообщение не уходило, у клиента есть согласие на этот канал.

Имена задач детерминированы:
    booking-owner-{id} / booking-confirmed-{id}
    booking-reminder-day-before-{id} / booking-reminder-same-day-{id}
Уникальный индекс по имени и есть идемпотентность: повторный вызов планировщика
дублей не создаёт.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from ..db import Notification, Store
from ..events import event as log_event
from ..policies import normalize_phone, signed_action, to_international
from ..tenants import Tenant, registry
from ..timeutil import human_date, norm_lang, tz as zone, zoned
from . import providers, templates

log = logging.getLogger("notify")

MAX_ATTEMPTS = 3
BACKOFF_MINUTES = (1, 5, 15)

# Сколько часов после назначенного времени сводка ещё имеет смысл.
DIGEST_WINDOW_HOURS = 3


def _minutes(hhmm: str) -> int:
    """«10:30» → 630. Часы салона в конфигурации хранятся строкой."""
    parts = str(hhmm or "0:00").split(":")
    return int(parts[0]) * 60 + (int(parts[1]) if len(parts) > 1 else 0)


@dataclass
class NotifySettings:
    enabled: bool = True
    provider: str = "console"
    owner_provider: str = "console"
    owner_recipient: str = ""
    client_channel: str = "whatsapp"
    language: str = "ru"
    sms_fallback: bool = True
    day_before_at: str = "19:00"
    same_day_hours: float = 3.0
    same_day_not_before: str = "09:00"
    review_after_hours: float = 2.0
    status_callback_url: str = ""
    # Личная ссылка есть только у пересозданных шаблонов. Выключено — уходит
    # прежний набор переменных, без неё.
    manage_button: bool = False
    overrides: dict = field(default_factory=dict)
    twilio: dict = field(default_factory=dict)
    telegram: dict = field(default_factory=dict)
    smtp: dict = field(default_factory=dict)

    def provider_cfg(self, provider: str, kind: str = "", lang: str = "") -> dict:
        """Настройки провайдера для конкретного сообщения.

        У просьбы об оценке и предложения места Content SID свой на каждый язык:
        утверждённый в Meta шаблон одноязычен, а эти два сообщения уходят на
        языке клиента. Нет шаблона на его языке — берём язык салона: испанский
        текст с рабочей кнопкой полезнее русского, который Meta не пропустит.
        """
        cfg = {"twilio": self.twilio, "telegram": self.telegram, "email": self.smtp}.get(provider, {})
        sids = (cfg.get("contentSids") or {}) if provider == "twilio" else {}
        if not (kind and isinstance(sids.get(kind), dict)):
            return cfg
        by_lang = sids[kind]
        sid = by_lang.get(norm_lang(lang or self.language)) or by_lang.get(norm_lang(self.language)) or ""
        return {**cfg, "contentSids": {**sids, kind: sid}}


def settings_for(tenant: Tenant) -> NotifySettings:
    n = tenant.notifications
    handoff = tenant.handoff
    telegram_token = handoff.get("telegramBotToken") or ""
    # Владельцу по умолчанию пишем в Telegram, если бот настроен: это не тратит
    # утверждённые шаблоны WhatsApp и не требует согласия.
    owner_provider = n.get("ownerProvider") or ("telegram" if telegram_token else n.get("provider") or "console")
    owner_recipient = (
        handoff.get("telegramChatId") if owner_provider == "telegram"
        else handoff.get("adminEmail") if owner_provider == "email"
        else (n.get("ownerPhone") or handoff.get("adminWhatsapp") or "")
    )
    return NotifySettings(
        enabled=n.get("enabled", True) is not False,
        provider=n.get("provider") or "console",
        owner_provider=owner_provider,
        owner_recipient=owner_recipient or "",
        client_channel=n.get("clientChannel") or "whatsapp",
        # `auto` из настроек AI сюда не годится: язык клиента в записи не
        # хранится, а утверждённый WhatsApp-шаблон всегда на одном языке.
        language=n.get("language") or "ru",
        sms_fallback=n.get("smsFallback", True) is not False,
        day_before_at=n.get("dayBeforeAt") or "19:00",
        same_day_hours=float(n.get("sameDayHours") or 3),
        same_day_not_before=n.get("sameDayNotBefore") or "09:00",
        review_after_hours=float(n.get("reviewAfterHours") or 2),
        status_callback_url=n.get("statusCallbackUrl") or "",
        manage_button=n.get("manageButtonTemplates") is True,
        overrides={
            "owner_new_booking": n.get("ownerTemplate"),
            "booking_confirmation": n.get("confirmationTemplate"),
            "booking_reminder_day_before": n.get("reminderDayBeforeTemplate"),
            "booking_reminder_today": n.get("reminderTodayTemplate"),
        },
        twilio={
            "accountSid": n.get("twilioAccountSid"),
            "authToken": n.get("twilioAuthToken"),
            "whatsappFrom": n.get("twilioWhatsappFrom"),
            "smsFrom": n.get("twilioSmsFrom"),
            "contentSids": {
                # Шаблон Meta одноязычен, поэтому у каждого типа свой SID на
                # язык. Поле без суффикса — испанский: оно появилось раньше
                # остальных, и переименовывать его в рабочем конфиге значит
                # оставить салон без подтверждений до правки в панели.
                "booking_confirmation": {
                    "es": n.get("contentSidConfirmation"), "ru": n.get("contentSidConfirmationRu"),
                    "en": n.get("contentSidConfirmationEn"),
                },
                "booking_reminder_day_before": {
                    "es": n.get("contentSidReminderDayBefore"),
                    "ru": n.get("contentSidReminderDayBeforeRu"),
                    "en": n.get("contentSidReminderDayBeforeEn"),
                },
                "booking_reminder_today": {
                    "es": n.get("contentSidReminderToday"),
                    "ru": n.get("contentSidReminderTodayRu"),
                    "en": n.get("contentSidReminderTodayEn"),
                },
                "booking_rescheduled": n.get("contentSidRescheduled"),
                "booking_cancelled": n.get("contentSidCancelled"),
                # Эти два — на языке клиента, поэтому шаблон на каждый язык свой.
                "review_request": {
                    "es": n.get("contentSidReviewEs"), "ru": n.get("contentSidReviewRu"),
                    "en": n.get("contentSidReviewEn"),
                },
                "waitlist_offer": {
                    "es": n.get("contentSidWaitlistEs"), "ru": n.get("contentSidWaitlistRu"),
                    "en": n.get("contentSidWaitlistEn"),
                },
            },
        },
        telegram={"botToken": telegram_token},
        smtp={
            "host": n.get("smtpHost"), "port": n.get("smtpPort"),
            "security": n.get("smtpSecurity"), "username": n.get("smtpUsername"),
            "password": n.get("smtpPassword"), "from": n.get("smtpFrom"),
        },
    )


def public_base_url(tenant: Tenant | None = None) -> str:
    """Адрес, по которому клиент откроет ссылку из сообщения.

    Источников три, по убыванию силы: переменная окружения, домен для клиентских
    ссылок из настроек бизнеса (`clientBaseUrl`) и адрес, который сервис запомнил
    сам, когда владелец открывал панель (`publicBaseUrl`). Последнее снимает
    ручной шаг: не задал ничего — ссылки всё равно работают, как только он хоть
    раз зашёл в панель по рабочему домену. Воркер берёт то же значение из общего
    тома с настройками: заголовков запроса у него нет.

    Явная настройка нужна там, где доменов несколько: панель открывают по
    `admin.…`, и запомненный адрес уводил клиентские ссылки туда же — вместе с
    кнопкой утверждённого шаблона, у которой в Meta зашит `bookings.…`.

    Пусто — значит ссылок в сообщениях не будет: об этом громко пишем в лог,
    иначе «отзывы не работают» выясняется по молчанию клиентов, а не по журналу.
    """
    base = (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")
    if not base and tenant is not None:
        base = (str(tenant.integration.get("clientBaseUrl") or "").rstrip("/")
                or str(tenant.integration.get("publicBaseUrl") or "").rstrip("/"))
    if not base and not _base_warned:
        _warn_no_base()
    return base


_base_warned = False


def _warn_no_base() -> None:
    global _base_warned  # noqa: PLW0603 — предупреждаем один раз за жизнь процесса
    _base_warned = True
    log.error("Публичный адрес сервиса неизвестен: ссылки на оценку визита, лист ожидания "
              "и «мои записи» в сообщения не попадут. Задайте PUBLIC_BASE_URL или откройте "
              "панель по рабочему домену — адрес запомнится сам.")


# Типы сообщений, под которыми уместна ссылка на свои записи: там, где клиенту
# может понадобиться подтвердить, перенести или отменить визит.
MANAGEABLE = ("booking_confirmation", "booking_rescheduled",
              "booking_reminder_day_before", "booking_reminder_today")


def link_tail(entity_id: str, slug: str, token: str, lang: str) -> str:
    """Хвост личной ссылки: всё, что меняется от клиента к клиенту.

    В утверждённом шаблоне Meta разрешает подставлять только окончание адреса
    кнопки — начало (`https://…/review/`) зашито в сам шаблон и без повторной
    модерации не меняется. Отсюда правило: сменили публичный адрес сервиса —
    шаблоны с кнопкой нужно пересоздать, иначе кнопка ведёт на старый домен.
    """
    return f"{entity_id}?tenant={slug}&token={token}&lang={norm_lang(lang)}"


def dump_variables(kind: str, values: dict[str, str]) -> str:
    """Переменные шаблона в задаче: JSON в порядке нумерации Meta."""
    return json.dumps(templates.ordered_variables(kind, values), ensure_ascii=False)


def task_variables(task: Notification) -> dict[str, str]:
    """Переменные из задачи. Испорченный JSON не должен ронять воркер целиком:
    без переменных сообщение уйдёт обычным текстом, и это видно в логе."""
    try:
        values = json.loads(task.variables or "{}")
    except ValueError:
        log.error("%s: переменные шаблона не читаются", task.notification_id)
        return {}
    return values if isinstance(values, dict) else {}


def manage_tail(tenant: Tenant, booking, lang: str) -> str:
    """Хвост личной ссылки на свои записи — то, что уезжает в адрес кнопки."""
    client_id = getattr(booking, "client_id", "") or ""
    if not client_id:
        return ""
    return link_tail(client_id, tenant.slug, signed_action("manage", tenant.slug, client_id), lang)


def manage_link(tenant: Tenant, booking, lang: str) -> str:
    """Личная ссылка клиента на свои записи. Пустая, если клиента ещё нет."""
    base = public_base_url(tenant)
    tail = manage_tail(tenant, booking, lang)
    return f"{base}/manage/{tail}" if (base and tail) else ""


def _owner_channel(provider: str) -> str:
    return "telegram" if provider == "telegram" else "email" if provider == "email" else "whatsapp"


# --- расчёт времени напоминаний ----------------------------------------------

def _shift_days(date_key: str, days: int) -> str:
    return (date.fromisoformat(date_key) + timedelta(days=days)).isoformat()


def reminder_times(booking, tenant: Tenant, s: NotifySettings,
                   now: datetime | None = None) -> dict[str, datetime | None]:
    """Когда слать напоминания.

    ``None`` означает «момент уже прошёл»: запись «на через час» не должна
    получить вчерашнее напоминание.
    """
    now = now or datetime.now(timezone.utc)
    tz_name = tenant.timezone
    start = booking.start_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    day_key = templates.local_date_key(start, tz_name)

    day_before = zoned(_shift_days(day_key, -1), s.day_before_at, tz_name)

    same_day = start - timedelta(hours=s.same_day_hours)
    not_before = zoned(day_key, s.same_day_not_before, tz_name)
    # Запись в 10 утра не должна будить клиента в 7 — сдвигаем на начало дня.
    if same_day < not_before:
        same_day = not_before
    # ...но и после начала записи напоминание бессмысленно.
    if same_day >= start:
        same_day = start - timedelta(minutes=30)

    return {
        "day_before": day_before if now < day_before < start else None,
        "same_day": same_day if now < same_day else None,
    }


# Позже этого времени просить оценку уже поздно: сообщение уйдёт утром.
REVIEW_NOT_AFTER = "21:00"


def review_time(booking, tenant: Tenant, s: NotifySettings, now: datetime | None = None) -> datetime:
    """Когда просить оценку: через пару часов после визита, но не ночью.

    Отсчёт от конца визита, а не от нажатия «пришёл»: отметить запись владелец
    может и через сутки, и разом за всю неделю — просьба «оцените визит» должна
    приходить, пока клиент ещё помнит, как всё прошло, а не когда до неё дошли
    руки. Отметку задним числом это тоже учитывает: раньше `now` не отправим.
    """
    now = now or datetime.now(timezone.utc)
    end = getattr(booking, "end_at", None) or booking.start_at
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    when = max(end, now) + timedelta(hours=s.review_after_hours)

    tz_name = tenant.timezone
    day_key = templates.local_date_key(when, tz_name)
    morning = zoned(day_key, s.same_day_not_before, tz_name)
    evening = zoned(day_key, REVIEW_NOT_AFTER, tz_name)
    if when < morning:
        return morning
    if when > evening:
        return zoned(_shift_days(day_key, 1), s.same_day_not_before, tz_name)
    return when


# --- сервис -------------------------------------------------------------------

class NotificationService:
    def __init__(self, store: Store) -> None:
        self.store = store

    def _tenant(self, slug: str) -> Tenant | None:
        try:
            return registry.get(slug)
        except Exception:  # noqa: BLE001 — бизнес мог быть удалён после планирования
            return None

    # --- планирование ---------------------------------------------------------
    def schedule_for_booking(self, booking, tenant: Tenant) -> list[Notification]:
        """Весь набор уведомлений по подтверждённой записи.

        Вызывать только после реального ответа календаря: пока события нет,
        «вы записаны» клиенту обещать нельзя.
        """
        s = settings_for(tenant)
        if not s.enabled:
            return []

        now = datetime.now(timezone.utc)
        created: list[Notification | None] = []

        # Владельцу — сразу и без согласия: это его собственная запись. Без
        # получателя задачу не ставим: она гарантированно падает в `failed` с
        # «Не указан получатель» на каждой записи и засоряет очередь. Своих
        # теперь оповещает список ниже, а этот канал остаётся для телефона или
        # отдельного чата, заданных в настройках.
        if str(s.owner_recipient or "").strip():
            created.append(self.store.enqueue_notification(
                notification_id=f"booking-owner-{booking.id}",
                tenant_id=tenant.slug, booking_id=booking.id,
                type="owner_new_booking", audience="owner",
                provider=s.owner_provider,
                channel=_owner_channel(s.owner_provider),
                recipient=s.owner_recipient, scheduled_at=now,
                booking_start_at=booking.start_at,
            ))

        # Своим — владельцу и администраторам, у кого привязан чат и не выключены
        # уведомления. Чат, который уже получает задачу владельца, пропускаем:
        # иначе один человек получает два одинаковых сообщения о записи.
        if s.telegram.get("botToken"):
            taken = {str(s.owner_recipient or "").strip()} if s.owner_provider == "telegram" else set()
            for person in self.store.staff_recipients():
                if person["chatId"] in taken:
                    continue
                taken.add(person["chatId"])
                created.append(self.store.enqueue_notification(
                    notification_id=f"booking-staff-{person['id']}-{booking.id}",
                    tenant_id=tenant.slug, booking_id=booking.id,
                    type="owner_new_booking", audience="staff",
                    provider="telegram", channel="telegram",
                    recipient=person["chatId"], scheduled_at=now,
                    booking_start_at=booking.start_at,
                ))

        # Мастеру — своя запись, в свой чат. Без привязанного чата задачу не
        # ставим вовсе: `failed` с «Не указан получатель» на каждой записи
        # засоряет очередь и ничего не сообщает — мастер просто не подключён.
        master_chat = str((tenant.master(booking.master_id) or {}).get("telegramChatId") or "").strip()
        if master_chat and s.telegram.get("botToken"):
            created.append(self.store.enqueue_notification(
                notification_id=f"booking-master-{booking.id}",
                tenant_id=tenant.slug, booking_id=booking.id,
                type="master_new_booking", audience="master",
                provider="telegram", channel="telegram",
                recipient=master_chat, scheduled_at=now,
                booking_start_at=booking.start_at,
            ))

        if getattr(booking, "notify_consent", True):
            created.append(self._client_task(booking, tenant, s,
                                             f"booking-confirmed-{booking.id}",
                                             "booking_confirmation", now))
            times = reminder_times(booking, tenant, s, now)
            if times["day_before"]:
                created.append(self._client_task(booking, tenant, s,
                                                 f"booking-reminder-day-before-{booking.id}",
                                                 "booking_reminder_day_before", times["day_before"]))
            if times["same_day"]:
                created.append(self._client_task(booking, tenant, s,
                                                 f"booking-reminder-same-day-{booking.id}",
                                                 "booking_reminder_today", times["same_day"]))

        # Для клиентов с историей неявок дедлайн подтверждения становится
        # реальным правилом, а не только значком в базе. После дедлайна слот
        # освобождается и сразу предлагается листу ожидания.
        if booking.requires_confirmation and s.owner_recipient:
            hours = int(tenant.policy("confirmationDeadlineHours", 4) or 4)
            deadline = booking.start_at - timedelta(hours=max(1, hours))
            if now < deadline:
                created.append(self.store.enqueue_notification(
                    notification_id=f"booking-confirmation-check-{booking.id}",
                    tenant_id=tenant.slug, booking_id=booking.id,
                    type="confirmation_check", audience="owner",
                    provider=s.owner_provider, channel=_owner_channel(s.owner_provider),
                    recipient=s.owner_recipient,
                    body=(f"Клиент {booking.client_name} не подтвердил визит. "
                          "Запись отменена, окно предложено листу ожидания."),
                    scheduled_at=deadline, booking_start_at=booking.start_at))

        return [t for t in created if t]

    def _client_task(self, booking, tenant: Tenant, s: NotifySettings,
                     notification_id: str, kind: str, run_at: datetime) -> Notification | None:
        # В базе телефон лежит как ввёл клиент — местным форматом, без кода
        # страны. Провайдеру нужен E.164, иначе «099000101» уходит как
        # «+099000101» и отвергается: подтверждение не доходит, а в логе это
        # выглядит проблемой Twilio, а не нашей.
        #
        # Язык берём из записи, как у просьбы об оценке: человек записался
        # по-русски, а подтверждение приходило на испанском — язык салона стоял
        # в настройках, и никого не спрашивали. Нет шаблона на его языке —
        # `provider_cfg` сам возьмёт язык салона.
        return self.store.enqueue_notification(
            notification_id=notification_id,
            tenant_id=tenant.slug, booking_id=booking.id,
            type=kind, audience="client",
            provider=s.provider, channel=s.client_channel,
            recipient=to_international(booking.phone, tenant.salon.get("phoneCountry")),
            lang=norm_lang(getattr(booking, "lang", "") or s.language),
            scheduled_at=run_at,
            booking_start_at=booking.start_at,
        )

    # --- утренняя сводка владельцу -------------------------------------------
    def schedule_owner_digest(self, tenant: Tenant, *, moment: datetime | None = None) -> Notification | None:
        """Сводка дня владельцу. Ставится утром и уходит сразу.

        Задача не планируется с вечера намеренно: за ночь запись отменяют,
        переносят и добавляют, а сводка, собранная заранее, врёт ровно про то,
        ради чего её читают. Имя задачи содержит дату — сколько бы раз воркер
        ни прошёл за утро, сводка уйдёт одна.

        Окно — три часа от назначенного времени. Воркер, поднявшийся к вечеру
        после простоя, «утреннюю сводку» уже не шлёт: в шесть вечера она не
        сообщает ничего, чего владелец не знает сам.
        """
        s = settings_for(tenant)
        n = tenant.notifications
        if not s.enabled or n.get("dailyDigest", True) is False:
            return None
        if not str(s.owner_recipient or "").strip():
            return None

        local = (moment or datetime.now(timezone.utc)).astimezone(zone(tenant.timezone))
        date_key = local.date().isoformat()
        start = zoned(date_key, str(n.get("digestAt") or "08:00"), tenant.timezone)
        if not start <= local < start + timedelta(hours=DIGEST_WINDOW_HOURS):
            return None

        return self.store.enqueue_notification(
            notification_id=f"owner-digest-{tenant.slug}-{date_key}",
            tenant_id=tenant.slug, booking_id="", type="owner_digest", audience="owner",
            provider=s.owner_provider, channel=_owner_channel(s.owner_provider),
            recipient=s.owner_recipient, scheduled_at=datetime.now(timezone.utc),
            body=self.digest_text(tenant, date_key),
        )

    def digest_text(self, tenant: Tenant, date_key: str) -> str:
        """Текст сводки. Читает его владелец — значит, по-русски и в пять строк."""
        from ..slots import work_hours, working_day

        tz = tenant.timezone
        day_start = zoned(date_key, "00:00", tz)
        today = self.store.day_bookings(tenant_id=tenant.slug, start=day_start,
                                        end=day_start + timedelta(days=1))
        yesterday = self.store.day_bookings(tenant_id=tenant.slug,
                                            start=day_start - timedelta(days=1), end=day_start)

        waiting = [b for b in today if b.requires_confirmation and not b.confirmed_by_client]
        done = [b for b in yesterday if b.status == "completed"]
        revenue = sum(int(b.paid_amount or 0) for b in done)
        currency = next((b.currency for b in done if b.currency), tenant.salon.get("currency") or "UYU")
        no_shows = sum(1 for b in yesterday if b.status == "no_show")

        # Загрузка — из смен и записей, без обращения к Google: сводка не имеет
        # права ждать чужой календарь, а свободные часы видны и так.
        busy = sum((b.end_at - b.start_at).total_seconds() / 60 for b in today)
        capacity = sum(
            _minutes(hours["end"]) - _minutes(hours["start"])
            for master in tenant.masters if working_day(tenant, master, date_key)
            for hours in [work_hours(tenant, master, date_key)]
        )
        free = max(0, capacity - int(busy))

        lines = [f"☀️ {tenant.salon.get('name') or tenant.slug}, {human_date(date_key)}",
                 f"Записей сегодня: {len(today)}"]
        for b in sorted(today, key=lambda x: x.start_at)[:5]:
            service = (tenant.service(b.service_id) or {}).get("title", b.service_id)
            master = (tenant.master(b.master_id) or {}).get("name", b.master_id)
            lines.append(f"  {b.start_at.astimezone(day_start.tzinfo).strftime('%H:%M')} "
                         f"{b.client_name} · {service} · {master}")
        if len(today) > 5:
            lines.append(f"  …и ещё {len(today) - 5}")
        if waiting:
            lines.append(f"Ждут подтверждения: {len(waiting)} — "
                         + ", ".join(b.client_name for b in waiting[:3]))
        if capacity:
            lines.append(f"Свободно {free // 60} ч из {capacity // 60} ч рабочего времени")
        lines.append(f"Вчера: {len(done)} визитов, {revenue} {currency}"
                     + (f", неявок {no_shows}" if no_shows else ""))
        return "\n".join(lines)

    def notify_manager(self, tenant: Tenant, phone: str, text: str) -> None:
        """Эскалация менеджеру — отправляем сразу, в обход очереди.

        Очередь нужна напоминаниям (их можно и нужно отменять); живой диалог,
        где клиент ждёт человека, откладывать на воркер нельзя.
        """
        s = settings_for(tenant)
        provider = s.provider if s.provider != "console" else "console"
        result = providers.send(
            provider=provider, channel="whatsapp", to=phone, body=text,
            template_name="handoff", cfg=s.provider_cfg(provider),
        )
        log.warning("Эскалация менеджеру (%s): %s", result.status, tenant.slug)

    def notify_staff_client_reply(self, tenant: Tenant, phone: str, text: str,
                                  client_name: str = "") -> int:
        """Клиент ответил в WhatsApp — показать это людям, а не потерять.

        В подтверждении и напоминаниях написано «ответьте на это сообщение».
        Пока ответ было некуда доставлять, клиент писал в пустоту: бизнес-номер
        принимал сообщение, и на этом всё заканчивалось.

        Задачи ставятся в очередь, а не отправляются на месте: у Telegram свои
        сбои и повторы, и ответ клиента — не то, что можно потерять из-за
        секундной недоступности.
        """
        s = settings_for(tenant)
        if not s.telegram.get("botToken"):
            log.warning("Ответ клиента %s некуда доставить: Telegram-бот не подключён", phone)
            return 0

        who = f"{client_name} ({phone})" if client_name else phone
        body = f"Ответ клиента {who}:\n\n{text}"
        now = datetime.now(timezone.utc)
        # Метка времени в имени: второй ответ того же клиента — отдельная
        # задача, а не «уже поставлено» из-за идемпотентности по имени.
        stamp = int(now.timestamp())
        chats: list[str] = []
        if s.owner_provider == "telegram" and str(s.owner_recipient or "").strip():
            chats.append(str(s.owner_recipient).strip())
        for person in self.store.staff_recipients():
            if person["chatId"] not in chats:
                chats.append(person["chatId"])

        sent = 0
        for chat in chats:
            made = self.store.enqueue_notification(
                notification_id=f"client-reply-{normalize_phone(phone)}-{chat}-{stamp}",
                # Пустая строка, а не None: колонка не допускает NULL — так же
                # живут рассылка и предложение из листа ожидания.
                tenant_id=tenant.slug, booking_id="",
                type="owner_client_reply", audience="staff",
                provider="telegram", channel="telegram",
                recipient=chat, body=body, scheduled_at=now,
            )
            sent += 1 if made else 0
        return sent

    def cancel_for_booking(self, booking_id: str, reason: str = "booking_cancelled") -> int:
        """Отмена записи — все будущие напоминания снимаются."""
        return self.store.cancel_notifications(booking_id, reason)

    def notify_client_cancelled(self, booking, tenant: Tenant) -> Notification | None:
        """Клиенту — что визита не будет. Отменяет салон, а приходит клиент.

        Ставится после `cancel_for_booking`, а не вместе с ним: тот снимает по
        записи всё подряд, и задача, созданная раньше, сняла бы саму себя.

        Прошедшую запись молчим: «ваша запись отменена» через день после того,
        как человек уже не пришёл, — это не забота, а недоумение.
        """
        s = settings_for(tenant)
        if not s.enabled or not getattr(booking, "notify_consent", True):
            return None
        start = booking.start_at if booking.start_at.tzinfo else booking.start_at.replace(tzinfo=timezone.utc)
        if start <= datetime.now(timezone.utc):
            return None
        # Отметка времени в имени: запись могут отменить, вернуть и отменить
        # снова — второй раз это другая задача, а не «уже поставлено».
        stamp = int(datetime.now(timezone.utc).timestamp())
        return self.store.enqueue_notification(
            notification_id=f"booking-cancelled-{booking.id}-{stamp}",
            tenant_id=tenant.slug, booking_id=booking.id,
            type="booking_cancelled", audience="client",
            provider=s.provider, channel=s.client_channel,
            recipient=to_international(booking.phone, tenant.salon.get("phoneCountry")),
            lang=norm_lang(getattr(booking, "lang", "") or s.language),
            scheduled_at=datetime.now(timezone.utc),
            booking_start_at=booking.start_at,
        )

    def notify_master_cancelled(self, booking, tenant: Tenant) -> None:
        """Мастеру — что окно освободилось. Сразу, в обход очереди.

        Откладывать бессмысленно: ценность сообщения в том, что мастер узнает
        об освободившемся окне сегодня, а не в момент следующего тика. Сбой
        доставки саму отмену не отменяет — записываем в лог и живём дальше.
        """
        s = settings_for(tenant)
        chat_id = str((tenant.master(booking.master_id) or {}).get("telegramChatId") or "").strip()
        token = s.telegram.get("botToken")
        if not (s.enabled and chat_id and token):
            return
        try:
            providers.send(
                provider="telegram", channel="telegram", to=chat_id,
                body=templates.message_for("master_booking_cancelled", booking, tenant, s.overrides),
                template_name="master_booking_cancelled", cfg=s.provider_cfg("telegram"),
            )
        except providers.SendError as exc:
            log.error("Не удалось сообщить мастеру об отмене %s: %s", booking.id, exc)

    def reschedule_for_booking(self, booking, tenant: Tenant,
                               previous: dict | None = None) -> list[Notification]:
        """Перенос: старые задачи снимаются, новые создаются с новым временем.

        Имена задач получают отметку времени записи — прежние имена уже заняты
        отменёнными строками, а уникальный индекс не даст их переиспользовать.

        ``previous`` — мастер и время до переноса: старому мастеру нужно сказать,
        что запись от него ушла, иначе он останется ждать клиента.
        """
        self.cancel_for_booking(booking.id, "booking_rescheduled")
        s = settings_for(tenant)
        if not s.enabled:
            return []

        stamp = int(booking.start_at.timestamp())
        now = datetime.now(timezone.utc)
        # Своим — раньше клиента: перенос делает администратор, а мастер узнавал
        # о нём только из журнала, если сам туда заглядывал.
        created = self._staff_reschedule_tasks(booking, tenant, s, stamp, previous or {})
        if not getattr(booking, "notify_consent", True):
            return [t for t in created if t]

        times = reminder_times(booking, tenant, s)
        created.append(self._client_task(
            booking, tenant, s, f"booking-rescheduled-{booking.id}-{stamp}",
            "booking_rescheduled", now))
        if times["day_before"]:
            created.append(self._client_task(
                booking, tenant, s, f"booking-reminder-day-before-{booking.id}-{stamp}",
                "booking_reminder_day_before", times["day_before"]))
        if times["same_day"]:
            created.append(self._client_task(
                booking, tenant, s, f"booking-reminder-same-day-{booking.id}-{stamp}",
                "booking_reminder_today", times["same_day"]))
        return [t for t in created if t]

    def _staff_reschedule_tasks(self, booking, tenant: Tenant, s: NotifySettings,
                                stamp: int, previous: dict) -> list[Notification | None]:
        """Перенос глазами салона: мастер, владелец, администраторы.

        Набор получателей тот же, что у новой записи, — перенос для них ровно
        такое же изменение рабочего дня. Старый мастер попадает в список только
        когда запись действительно ушла к другому.
        """
        now = datetime.now(timezone.utc)
        created: list[Notification | None] = []
        base = dict(tenant_id=tenant.slug, booking_id=booking.id, scheduled_at=now,
                    booking_start_at=booking.start_at)

        if str(s.owner_recipient or "").strip():
            created.append(self.store.enqueue_notification(
                notification_id=f"booking-rescheduled-owner-{booking.id}-{stamp}",
                type="owner_booking_rescheduled", audience="owner",
                provider=s.owner_provider, channel=_owner_channel(s.owner_provider),
                recipient=s.owner_recipient, **base))

        if not s.telegram.get("botToken"):
            return created

        taken = {str(s.owner_recipient or "").strip()} if s.owner_provider == "telegram" else set()
        for person in self.store.staff_recipients():
            if person["chatId"] in taken:
                continue
            taken.add(person["chatId"])
            created.append(self.store.enqueue_notification(
                notification_id=f"booking-rescheduled-staff-{person['id']}-{booking.id}-{stamp}",
                type="owner_booking_rescheduled", audience="staff",
                provider="telegram", channel="telegram",
                recipient=person["chatId"], **base))

        master_chat = str((tenant.master(booking.master_id) or {}).get("telegramChatId") or "").strip()
        if master_chat:
            created.append(self.store.enqueue_notification(
                notification_id=f"booking-rescheduled-master-{booking.id}-{stamp}",
                type="master_booking_rescheduled", audience="master",
                provider="telegram", channel="telegram",
                recipient=master_chat, **base))

        # Запись сменила мастера: прежнему пишем готовым текстом — в шаблоне
        # стоит новое время, а ему важно именно то, которое у него было.
        old_id = str(previous.get("master_id") or "")
        old_start = previous.get("start_at")
        if old_id and old_id != booking.master_id and old_start:
            old_chat = str((tenant.master(old_id) or {}).get("telegramChatId") or "").strip()
            values = templates.variables_for(booking, tenant)
            if old_chat and old_chat != master_chat:
                created.append(self.store.enqueue_notification(
                    notification_id=f"booking-rescheduled-from-{old_id}-{booking.id}-{stamp}",
                    type="master_booking_rescheduled", audience="master",
                    provider="telegram", channel="telegram", recipient=old_chat,
                    body=(f"Запись ушла к другому мастеру: "
                          f"{human_date(templates.local_date_key(old_start, tenant.timezone))} "
                          f"в {templates.local_time(old_start, tenant.timezone)} — "
                          f"{values['service']}, {values['name']}. Окно освободилось."),
                    **base))
        return created

    def schedule_review(self, booking, tenant: Tenant) -> Notification | None:
        """Через пару часов после визита просим оценку; повторный вызов идемпотентен."""
        review = self.store.create_review(tenant_id=tenant.slug, booking_id=booking.id,
                                          client_id=booking.client_id)
        if not review:
            return None
        s = settings_for(tenant)
        base = public_base_url(tenant)
        if not base:
            # Без ссылки просить оценку бессмысленно: ответ «5» в WhatsApp
            # никто не разбирает, и клиент получает письмо в никуда.
            return None
        # Язык клиента, а не салона: он записан в самой записи с момента диалога.
        lang = norm_lang(getattr(booking, "lang", "") or s.language)
        token = signed_action("review", tenant.slug, review.id)
        tail = link_tail(review.id, tenant.slug, token, lang)
        values = templates.variables_for(booking, tenant, lang)
        return self.store.enqueue_notification(
            notification_id=f"booking-review-{booking.id}", tenant_id=tenant.slug,
            booking_id="", type="review_request", audience="client", provider=s.provider,
            channel=s.client_channel,
            recipient=to_international(booking.phone, tenant.salon.get("phoneCountry")),
            body=templates.link_message("review_request", lang, name=values["name"],
                                        salon=values["salon"], service=values["service"],
                                        link=f"{base}/review/{tail}"),
            lang=lang,
            variables=dump_variables("review_request", {**values, "link": tail}),
            scheduled_at=review_time(booking, tenant, s))

    def offer_waitlist(self, booking, tenant: Tenant) -> int:
        """Освободившийся слот предлагается всем подходящим; победит первый accept."""
        from sqlalchemy import select
        from ..db import Client, WaitlistEntry

        date_key = templates.local_date_key(booking.start_at, tenant.timezone)
        time_key = templates.local_time(booking.start_at, tenant.timezone)
        s = settings_for(tenant)
        made = 0
        with self.store.session_factory() as session:
            rows = list(session.execute(
                select(WaitlistEntry, Client).join(Client, Client.id == WaitlistEntry.client_id).where(
                    WaitlistEntry.tenant_id == tenant.slug, WaitlistEntry.status == "waiting",
                    WaitlistEntry.service_id == booking.service_id,
                    WaitlistEntry.date_from <= date_key, WaitlistEntry.date_to >= date_key,
                )).all())
            for entry, client in rows:
                if entry.master_id and entry.master_id != booking.master_id:
                    continue
                if entry.time_from and time_key < entry.time_from:
                    continue
                if entry.time_to and time_key > entry.time_to:
                    continue
                base = public_base_url(tenant)
                if not base:
                    # Забрать место без ссылки нельзя — предложение, на которое
                    # невозможно ответить, только раздражает.
                    continue
                token = signed_action("waitlist", tenant.slug, entry.id)
                lang = norm_lang(client.lang or s.language)
                tail = link_tail(entry.id, tenant.slug, token, lang)
                values = {
                    "name": client.name or "",
                    "service": tenant.localized(tenant.service(booking.service_id) or {}, "title", lang)
                    or booking.service_id,
                    "date": templates.human_date(date_key, lang),
                    "time": time_key,
                }
                task = self.store.enqueue_notification(
                    notification_id=f"waitlist-offer-{entry.id}-{booking.id}", tenant_id=tenant.slug,
                    booking_id="", type="waitlist_offer", audience="client", provider=s.provider,
                    channel=s.client_channel,
                    recipient=to_international(client.phone, tenant.salon.get("phoneCountry")),
                    body=templates.link_message("waitlist_offer", lang,
                                                link=f"{base}/waitlist/{tail}", **values),
                    lang=lang,
                    variables=dump_variables("waitlist_offer", {**values, "link": tail}),
                    scheduled_at=datetime.now(timezone.utc))
                if task:
                    made += 1
                    entry.status, entry.offered_booking_id = "offered", booking.id
                    entry.offer_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
            session.commit()
        return made

    # --- отправка -------------------------------------------------------------
    def guard(self, task: Notification):
        """Перепроверка прямо перед отправкой.

        Здесь и отсекается отменённая или перенесённая запись: между постановкой
        задачи и её отправкой могут пройти сутки.
        """
        # Рассылка и предложение из листа ожидания живут без записи: у них готовый
        # текст. Возвращаем `None`, а не «истину»: дальше по коду это значение
        # уходит в шаблоны и в уведомление о недоставке, и `True.start_at`
        # роняло воркер на каждом таком сообщении.
        if (task.type in ("campaign", "review_request", "waitlist_offer",
                          "owner_client_reply", "owner_digest") and task.body):
            return None, None
        booking = self.store.get_booking(task.booking_id, tenant_id=task.tenant_id)
        if not booking:
            return None, "запись не найдена"
        # Сообщению об отмене отменённая запись и нужна: для всех остальных это
        # причина молчать, а для него — причина уйти.
        expected = "cancelled" if task.type == "booking_cancelled" else "confirmed"
        if booking.status != expected:
            return None, f"статус записи: {booking.status}"

        start = booking.start_at if booking.start_at.tzinfo else booking.start_at.replace(tzinfo=timezone.utc)
        if task.booking_start_at:
            snapshot = (task.booking_start_at if task.booking_start_at.tzinfo
                        else task.booking_start_at.replace(tzinfo=timezone.utc))
            if abs((start - snapshot).total_seconds()) > 1:
                return None, "время записи изменилось"

        # Согласие спрашивают у клиента; мастеру о его собственной смене пишем
        # всегда — это рабочее расписание, а не рассылка.
        if task.audience == "client" and not booking.notify_consent:
            return None, "нет согласия на сообщения"
        if (task.audience == "client" and task.type != "booking_confirmation"
                and start <= datetime.now(timezone.utc)):
            return None, "запись уже началась"
        return booking, None

    def run_task(self, task: Notification) -> str:
        """Одна задача: проверка, отправка, фиксация результата. Возвращает статус."""
        tenant = self._tenant(task.tenant_id)
        if not tenant:
            self.store.patch_notification(task.notification_id,
                                          {"status": "cancelled", "error": "бизнес не найден"})
            return "cancelled"

        booking, reason = self.guard(task)
        if reason:
            self.store.patch_notification(task.notification_id, {"status": "cancelled", "error": reason})
            return "cancelled"

        if task.type == "confirmation_check":
            if booking.confirmed_by_client:
                self.store.patch_notification(task.notification_id,
                                              {"status": "cancelled", "error": "клиент подтвердил"})
                return "cancelled"
            self.store.set_booking_status(booking.id, "cancelled", tenant_id=tenant.slug)
            self.offer_waitlist(booking, tenant)

        s = settings_for(tenant)
        # Клиенту — на языке салона, владельцу — на языке панели: сообщение о
        # новой записи читает он сам, и переводить его незачем. Просьба об
        # оценке и предложение места собраны заранее и на языке клиента —
        # у них язык записан в самой задаче.
        lang = task.lang or (s.language if task.audience == "client" else "ru")
        # Своим под сообщением — кнопки «пришёл / не пришёл / отменить»: увидев
        # запись, отметить её надо там же, а не открывая панель.
        buttons = None
        if task.channel == "telegram" and task.type in (
                "owner_new_booking", "master_new_booking",
                "owner_booking_rescheduled", "master_booking_rescheduled"):
            from ..telegram_bot import booking_buttons
            buttons = booking_buttons(booking.id)
        # Шаблон вычисляем до отправки: в лог уходит, ушло сообщение утверждённым
        # шаблоном или обычным текстом. Иначе «а кнопка-то была?» проверяется
        # только по скриншоту от клиента — Twilio в списке сообщений про шаблон
        # не рассказывает.
        cfg = s.provider_cfg(task.provider, task.type, lang)
        template = (cfg.get("contentSids") or {}).get(task.type) or "" if task.provider == "twilio" else ""
        try:
            result = providers.send(
                provider=task.provider, channel=task.channel, to=task.recipient,
                body=task.body or self.client_body(task, booking, tenant, s, lang),
                template_name=task.type, buttons=buttons,
                variables=self.template_variables(task, booking, tenant, s, lang),
                cfg=cfg,
                status_callback=s.status_callback_url if task.audience == "client" else None,
            )
        except providers.SendError as exc:
            log_event("notify.failed", tenant=task.tenant_id, type=task.type,
                      audience=task.audience, channel=task.channel,
                      provider=task.provider, booking=task.booking_id, reason=str(exc))
            return self._handle_failure(task, booking, s, exc)

        self.store.patch_notification(task.notification_id, {
            "status": result.status,
            "provider_message_id": result.provider_message_id,
            "sent_at": datetime.now(timezone.utc),
            "attempts": (task.attempts or 0) + 1,
            "error": None,
        })
        log_event("notify.sent", tenant=task.tenant_id, type=task.type,
                  audience=task.audience, channel=task.channel, lang=lang,
                  template=template or "text",
                  provider=task.provider, status=result.status, booking=task.booking_id)
        return result.status

    def template_variables(self, task: Notification, booking, tenant: Tenant,
                           s: NotifySettings, lang: str) -> dict[str, str]:
        """Переменные утверждённого шаблона.

        Просьба об оценке и предложение места несут свои переменные с момента
        постановки — записи под рукой у них нет. Остальным набор собирается из
        полей записи, и к сообщениям с кнопкой добавляется хвост личной ссылки:
        тело шаблона менять нельзя, а адрес кнопки Meta разрешает достраивать.
        """
        if task.variables:
            return task_variables(task)
        if not booking:
            return {}
        values = templates.variables_for(booking, tenant, lang)
        manage = s.manage_button and task.audience == "client"
        if manage and task.type in templates.MANAGE_BUTTON_TEMPLATES:
            # В тексте нужен полный адрес, в кнопке — только хвост: начало
            # адреса у неё зашито в самом шаблоне. Где ссылка стоит, знает сам
            # текст шаблона — отдельный флаг тенанта тут уже разъезжался с Meta.
            values["link"] = (manage_link(tenant, booking, lang)
                              if templates.link_in_body(task.type, lang)
                              else manage_tail(tenant, booking, lang))
            if not values["link"]:
                # Сообщение всё равно уходит: узнать о записи важнее, чем
                # открыть её одним нажатием.
                log.warning("%s: нет личной ссылки, сообщение уйдёт без неё",
                            task.notification_id)
        return templates.ordered_variables(task.type, values, manage)

    def client_body(self, task: Notification, booking, tenant: Tenant,
                    s: NotifySettings, lang: str) -> str:
        """Текст сообщения плюс ссылка на свои записи, где она уместна.

        Ссылка идёт отдельной строкой после шаблона: тело утверждённого в Meta
        шаблона менять нельзя без повторной модерации, а при отправке через
        Content SID это поле вообще не используется — там ссылка появится
        только вместе с новой версией шаблона.
        """
        if booking is None:
            return task.body or ""
        link = manage_link(tenant, booking, lang) if task.audience == "client" else ""
        body = templates.message_for(task.type, booking, tenant, s.overrides, lang,
                                     link=link)
        if task.audience != "client" or task.type not in MANAGEABLE or not link:
            return body
        # Ссылка уже стоит в самом тексте — второй раз отдельной строкой её
        # приписывать незачем.
        if templates.has_link(task.type, lang, s.overrides):
            return body
        return f"{body}\n\n{templates.link_message('manage_hint', lang, link=link)}"

    def _handle_failure(self, task: Notification, booking, s: NotifySettings,
                        exc: providers.SendError) -> str:
        attempts = (task.attempts or 0) + 1
        if not exc.permanent and attempts < MAX_ATTEMPTS:
            delay = BACKOFF_MINUTES[min(attempts - 1, len(BACKOFF_MINUTES) - 1)]
            self.store.patch_notification(task.notification_id, {
                "status": "scheduled", "attempts": attempts, "error": exc.message,
                "scheduled_at": datetime.now(timezone.utc) + timedelta(minutes=delay),
            })
            return "scheduled"

        self.store.patch_notification(task.notification_id,
                                      {"status": "failed", "attempts": attempts, "error": exc.message})
        log.error("%s → %s", task.notification_id, exc.message)
        self._after_failure(task, booking, s)
        return "failed"

    def _after_failure(self, task: Notification, booking, s: NotifySettings) -> None:
        """SMS как резерв; если резерва нет — предупреждаем владельца."""
        if self._enqueue_sms_fallback(task, s):
            return
        if task.audience == "client":
            self._alert_owner(task, booking, s)

    def _enqueue_sms_fallback(self, task: Notification, s: NotifySettings) -> Notification | None:
        """SMS только если не ушёл WhatsApp, и только один раз.

        Без купленного SMS-номера резерв бессмыслен: задача встаёт в очередь и
        падает с «не задан номер отправителя для sms» — на каждой недоставке,
        пряча настоящую причину среди своих же ошибок.
        """
        if not s.sms_fallback or task.audience != "client" or task.channel != "whatsapp":
            return None
        if s.provider == "twilio" and not (s.twilio.get("smsFrom") or "").strip():
            log.info("SMS-резерв пропущен: у Twilio не задан SMS-номер")
            return None
        return self.store.enqueue_notification(
            notification_id=f"{task.notification_id}-sms",
            tenant_id=task.tenant_id, booking_id=task.booking_id,
            type=task.type, audience="client", provider=task.provider, channel="sms",
            recipient=task.recipient, scheduled_at=datetime.now(timezone.utc),
            booking_start_at=task.booking_start_at, fallback_of=task.notification_id,
            # Текст переносим целиком: у задач без записи (просьба об оценке,
            # предложение места, рассылка) собрать его заново неоткуда, и дубль
            # по SMS уходил пустым.
            body=task.body, lang=task.lang, variables=task.variables,
        )

    def _alert_owner(self, task: Notification, booking, s: NotifySettings) -> Notification | None:
        """«Клиенту не дошло» — своим в Telegram.

        Раньше это уходило единственным каналом владельца, и при пустом
        получателе новость о недоставке пропадала вместе с самой недоставкой.
        Теперь её получают все, кто получает и записи: узнать, что клиент не
        предупреждён, важнее всего именно тем, кто его ждёт.
        """
        now = datetime.now(timezone.utc)
        start = booking.start_at if booking else None
        made: Notification | None = None

        if s.telegram.get("botToken"):
            taken = {str(s.owner_recipient or "").strip()} if s.owner_provider == "telegram" else set()
            for person in self.store.staff_recipients():
                if person["chatId"] in taken:
                    continue
                taken.add(person["chatId"])
                made = self.store.enqueue_notification(
                    notification_id=f"booking-alert-{person['id']}-{task.notification_id}",
                    tenant_id=task.tenant_id, booking_id=task.booking_id,
                    type="owner_delivery_failed", audience="staff",
                    provider="telegram", channel="telegram",
                    recipient=person["chatId"], scheduled_at=now, booking_start_at=start,
                ) or made

        if str(s.owner_recipient or "").strip():
            made = self.store.enqueue_notification(
                notification_id=f"booking-alert-{task.notification_id}",
                tenant_id=task.tenant_id, booking_id=task.booking_id,
                type="owner_delivery_failed", audience="owner",
                provider=s.owner_provider,
                channel=_owner_channel(s.owner_provider),
                recipient=s.owner_recipient, scheduled_at=now, booking_start_at=start,
            ) or made
        return made

    def tick(self, limit: int = 50) -> int:
        """Один проход по очереди. Захваченные задачи параллельный воркер не возьмёт."""
        due = self.store.claim_due_notifications(datetime.now(timezone.utc), limit=limit)
        for task in due:
            try:
                self.run_task(task)
            except Exception:  # noqa: BLE001 — одна задача не должна валить проход
                log.exception("Задача %s упала", task.notification_id)
                self.store.patch_notification(task.notification_id,
                                              {"status": "failed", "error": "внутренняя ошибка"})
        return len(due)

    # --- статусы от провайдера -----------------------------------------------
    def apply_provider_status(self, *, provider_message_id: str, raw_status: str) -> Notification | None:
        """Webhook доставки. Владельцу сообщаем только об окончательном провале."""
        status = providers.normalize_twilio_status(raw_status)
        if not (status and provider_message_id):
            return None
        task = self.store.notification_by_message_id(provider_message_id)
        if not task or task.status == "delivered":  # повторный webhook ничего не меняет
            return task

        patch = {"status": status}
        if status == "delivered":
            patch["delivered_at"] = datetime.now(timezone.utc)
        if status == "failed":
            patch["error"] = f"провайдер: {raw_status}"
        updated = self.store.patch_notification(task.notification_id, patch)

        if status == "failed":
            tenant = self._tenant(task.tenant_id)
            if tenant:
                booking = self.store.get_booking(task.booking_id, tenant_id=task.tenant_id)
                self._after_failure(task, booking, settings_for(tenant))
        return updated
