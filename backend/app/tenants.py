"""Реестр бизнесов.

Один сервис обслуживает много салонов. У каждого своя папка с конфигурацией,
свой виджет-сниппет и свои данные — записи и диалоги разделены tenant_id.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import threading
from pathlib import Path
from typing import Any

from .schema import ROOT, put, to_env, to_files, to_form, validate_config
from .secretstore import SECRET_PATHS
from .timeutil import norm_lang

TENANTS_DIR = ROOT / "tenants"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$")

_lock = threading.Lock()

DEFAULT_SALON = {
    "name": "Новый салон",
    "tagline": "",
    "address": "",
    "whatsapp": "",
    "instagram": "",
    "timezone": "America/Montevideo",
    "workHours": {"start": "10:00", "end": "20:00"},
    "workDays": [1, 2, 3, 4, 5, 6],
    "slotStepMinutes": 30,
    "bookingHorizonDays": 14,
    "leadTimeMinutes": 120,
    "services": [
        {"id": "haircut", "title": "Стрижка", "desc": "", "duration": 60, "price": "",
         "priceAmount": 0, "currency": "UYU", "groupCapacity": 1},
    ],
    "promotions": [],
    "masters": [
        {"id": "master-1", "name": "Мастер", "role": "", "services": ["haircut"],
         "workDays": [1, 2, 3, 4, 5, 6], "calendarId": "primary"},
    ],
}

DEFAULT_INTEGRATION = {
    "mode": "local",
    # Новый салон стартует на бесплатном провайдере: пробовать бота за деньги
    # никто не станет, а инструменты у всех провайдеров одинаковые.
    "ai": {"enabled": False, "provider": "groq", "model": "llama-3.3-70b-versatile",
           "maxSteps": 8, "timeoutSeconds": 30, "language": "ru"},
    "channel": {"kind": "web", "allowedOrigins": ""},
    "policies": {
        "requireExplicitConfirmation": True, "recheckSlotBeforeInsert": True,
        "idempotencyEnabled": True, "allowCancel": True, "allowReschedule": False,
        "maxBookingsPerPhonePerDay": 3, "rateLimitPerMinute": 20,
        "maskPiiInLogs": True, "dataRetentionDays": 180,
    },
    "handoff": {"autonomous": True, "escalateOnCalendarError": True, "escalateOnUnknownIntent": True,
                "handoffMessage": "Передаю ваш вопрос администратору — с вами свяжутся в ближайшее время."},
    "notifications": {
        "enabled": True, "provider": "console", "clientChannel": "whatsapp",
        "language": "ru", "smsFallback": True,
        # console, а не telegram: у нового бизнеса чат ещё не привязан, а канал
        # владельца без chatId — молчащий. Кнопка «Связать чат» переключит сама.
        "ownerProvider": "console", "dayBeforeAt": "19:00", "sameDayHours": 3,
        "sameDayNotBefore": "09:00",
    },
}

# Заполняется при старте приложения: секреты живут в окружении и в базе,
# и модуль конфигурации не должен ничего знать про SQLAlchemy.
_secrets = None


def bind_secret_store(secret_store) -> None:
    global _secrets  # noqa: PLW0603 — единственная точка связывания
    _secrets = secret_store


def _secret(slug: str, path: str) -> str:
    from .secretstore import from_env

    if _secrets is None:
        return from_env(path, slug)
    return _secrets.get(slug, path)


class TenantError(Exception):
    """Понятная ошибка для API: неверный slug, дубль, отсутствующий бизнес."""


def _read_json(path: Path, fallback: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return json.loads(json.dumps(fallback))


def _write_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


class Tenant:
    """Конфигурация одного бизнеса. Тот же интерфейс, что был у Settings."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.dir = TENANTS_DIR / slug
        self.salon = _read_json(self.dir / "salon.json", DEFAULT_SALON)
        self.integration = _read_json(self.dir / "integration.json", DEFAULT_INTEGRATION)

    # --- секреты ----------------------------------------------------------
    def secret(self, path: str) -> str:
        """Значение секрета: окружение сервера, затем база. В файлах их нет."""
        return _secret(self.slug, path)

    def has_secret(self, path: str) -> bool:
        return bool(self.secret(path))

    def _with_secrets(self, section: str | None) -> dict:
        """Срез конфигурации с подмешанными секретами — то, чем пользуется рантайм."""
        raw = self.integration.get(section, {}) if section else self.integration
        out = dict(raw or {})
        prefix = f"{section}." if section else ""
        for path in SECRET_PATHS:
            key = path[len(prefix):]
            if not path.startswith(prefix) or "." in key:
                continue
            value = self.secret(path)
            if value:
                out[key] = value
        return out

    # --- срезы ------------------------------------------------------------
    @property
    def title(self) -> str:
        return self.salon.get("name") or self.slug

    @property
    def timezone(self) -> str:
        return self.salon.get("timezone", "UTC")

    @property
    def default_lang(self) -> str:
        """Язык, на котором говорят с клиентом, когда его собственный неизвестен.

        Салону в Монтевидео русский по умолчанию не годится: страница записи без
        `?lang=` и входящее в WhatsApp от незнакомого номера обязаны заговорить
        по-испански. `auto` — не язык, а правило для модели, поэтому из него
        берём язык уведомлений: он у салона заполнен всегда.
        """
        for raw in (self.ai.get("language"), self.notifications.get("language")):
            code = (raw or "").strip().lower()[:2]
            if code and code != "au":
                return norm_lang(code)
        return "ru"

    @property
    def services(self) -> list[dict]:
        return self.salon.get("services", [])

    @property
    def masters(self) -> list[dict]:
        return self.salon.get("masters", [])

    @property
    def google(self) -> dict:
        """Корень integration.json вместе с секретами Google.

        Client ID секретом не считается и остаётся в файле, но общий на сервис
        ID из окружения имеет приоритет — так все бизнесы ходят через одно
        OAuth-приложение.
        """
        import os

        out = self._with_secrets(None)
        env_client_id = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()
        if env_client_id:
            out["clientId"] = env_client_id
        return out

    @property
    def ai(self) -> dict:
        return self._with_secrets("ai")

    @property
    def channel(self) -> dict:
        return self._with_secrets("channel") or {"kind": "web"}

    @property
    def policies(self) -> dict:
        return self.integration.get("policies", {})

    @property
    def sales(self) -> dict:
        return self.integration.get("sales", {"upsellEnabled": True, "upsellMaxPerDialog": 1,
                                              "upsellMoment": "after_booking", "fillGaps": True})

    @property
    def handoff(self) -> dict:
        return self._with_secrets("handoff")

    @property
    def autonomous(self) -> bool:
        """Бот доводит разговор до конца сам, без передачи администратору."""
        return bool(self.handoff.get("autonomous", True))

    @property
    def notifications(self) -> dict:
        return self._with_secrets("notifications")

    def service(self, service_id: str) -> dict | None:
        return next((s for s in self.services if s["id"] == service_id), None)

    @staticmethod
    def localized(item: dict, key: str, lang: str) -> str:
        """Значение поля на языке клиента: `titleEs`/`titleEn` рядом с `title`.

        Пустой перевод — не ошибка, а «пока не перевели»: показываем основной
        текст, а не пустоту. Русский и есть основной, суффикса у него нет.
        """
        base = item.get(key) or ""
        code = norm_lang(lang)
        if code == "ru":
            return base
        return item.get(f"{key}{code.capitalize()}") or base

    def master(self, master_id: str) -> dict | None:
        return next((m for m in self.masters if m["id"] == master_id), None)

    def policy(self, key: str, default: Any = None) -> Any:
        return self.policies.get(key, default)

    # --- форма ------------------------------------------------------------
    def form_data(self) -> dict:
        return to_form(self.salon, self.integration, self.has_secret)

    def env_preview(self) -> str:
        return to_env(self.integration, self.slug)

    def patch_integration(self, patch: dict) -> None:
        """Точечное изменение интеграции в обход формы — для кнопок подключения.

        Валидация формы здесь неуместна: у бизнеса может быть не заполнен адрес,
        но полученный от Google токен потерять нельзя. Секреты из патча уходят в
        хранилище, в файл попадает только всё остальное.

        Ключи бывают вложенными — ``handoff.telegramChatId``. Разбирать их здесь,
        а не в вызывающем коде, важнее, чем кажется: собрать патч самому — значит
        прочитать секцию через ``tenant.handoff``, где секреты уже подмешаны, и
        записать токен бота обратно в JSON-файл, который уезжает в репозиторий.
        """
        with _lock:
            for key in list(patch):
                if key in SECRET_PATHS:
                    self._save_secret(key, str(patch.pop(key) or ""))
            for key, value in patch.items():
                put(self.integration, key, value)
            self.dir.mkdir(parents=True, exist_ok=True)
            _write_json(self.dir / "integration.json", self.integration)

    def patch_salon(self, patch: dict) -> None:
        """Точечное изменение салона в обход формы — для кнопок привязки.

        Как и у интеграции, валидация формы здесь неуместна: привязанный чат
        мастера нельзя терять из-за того, что у салона не заполнен адрес.
        Секретов в salon.json нет, поэтому патч уходит в файл целиком.
        """
        with _lock:
            for key, value in patch.items():
                put(self.salon, key, value)
            self.dir.mkdir(parents=True, exist_ok=True)
            _write_json(self.dir / "salon.json", self.salon)

    def patch_master(self, master_id: str, patch: dict) -> dict:
        """Точечная правка карточки мастера в обход формы — для кнопок панели.

        Как и у интеграции: валидация формы здесь неуместна, иначе созданный
        календарь потерялся бы из-за незаполненного адреса салона.
        """
        with _lock:
            master = next((m for m in self.salon.get("masters", []) if m.get("id") == master_id), None)
            if master is None:
                raise TenantError(f"Мастера «{master_id}» нет")
            master.update(patch)
            self.dir.mkdir(parents=True, exist_ok=True)
            _write_json(self.dir / "salon.json", self.salon)
            return master

    def set_master_shift(self, master_id: str, date_str: str, shift: dict | None) -> dict:
        """Правка графика мастера на конкретный день.

        ``shift = None`` возвращает день к недельной сетке. Заодно вычищаются
        правки за прошедшие дни: календарь смен ведут месяцами, и без уборки
        salon.json за год копит сотни бесполезных строк.
        """
        from .timeutil import today_key

        with _lock:
            master = next((m for m in self.salon.get("masters", []) if m.get("id") == master_id), None)
            if master is None:
                raise TenantError(f"Мастера «{master_id}» нет")
            shifts = {k: v for k, v in (master.get("shifts") or {}).items()
                      if isinstance(v, dict) and k >= today_key(self.timezone)}
            if shift is None:
                shifts.pop(date_str, None)
            else:
                shifts[date_str] = shift
            master["shifts"] = dict(sorted(shifts.items()))
            self.dir.mkdir(parents=True, exist_ok=True)
            _write_json(self.dir / "salon.json", self.salon)
            return master["shifts"]

    def save_form(self, data: dict) -> tuple[bool, list[str]]:
        errors = validate_config(data)
        if errors:
            return False, errors
        salon, integration = to_files(data, self.integration, on_secret=self._save_secret,
                                      previous_salon=self.salon)
        with _lock:
            self.dir.mkdir(parents=True, exist_ok=True)
            _write_json(self.dir / "salon.json", salon)
            _write_json(self.dir / "integration.json", integration)
            self.salon, self.integration = salon, integration
        return True, []

    def _save_secret(self, path: str, value: str) -> None:
        if _secrets is not None:
            _secrets.set(self.slug, path, value)

    def sanitize_secrets(self) -> list[str]:
        """Переносит секреты из старого integration.json в хранилище и вычищает файл.

        Одноразовая миграция: прежние конфигурации лежали в репозитории вместе с
        токеном Telegram и ключом OpenAI.
        """
        if _secrets is None:
            return []
        from .schema import get as get_path

        moved: list[str] = []
        with _lock:
            for path in sorted(SECRET_PATHS):
                value = get_path(self.integration, path)
                if not isinstance(value, str) or not value:
                    self._drop_path(path)
                    continue
                if not _secrets.get(self.slug, path):
                    _secrets.set(self.slug, path, value)
                self._drop_path(path)
                moved.append(path)
            if moved:
                self.dir.mkdir(parents=True, exist_ok=True)
                _write_json(self.dir / "integration.json", self.integration)
        return moved

    def _drop_path(self, path: str) -> None:
        keys = path.split(".")
        node = self.integration
        for key in keys[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
            if not isinstance(node, dict):
                return
        node.pop(keys[-1], None)


class TenantRegistry:
    """Список бизнесов и операции над ними. Кэш сбрасывается при изменениях."""

    def __init__(self) -> None:
        TENANTS_DIR.mkdir(exist_ok=True)
        self._cache: dict[str, Tenant] = {}

    def slugs(self) -> list[str]:
        return sorted(p.name for p in TENANTS_DIR.iterdir()
                      if p.is_dir() and (p / "salon.json").exists())

    def exists(self, slug: str) -> bool:
        return (TENANTS_DIR / slug / "salon.json").exists()

    def get(self, slug: str) -> Tenant:
        if not self.exists(slug):
            raise TenantError(f"Бизнес «{slug}» не найден")
        if slug not in self._cache:
            tenant = Tenant(slug)
            moved = tenant.sanitize_secrets()
            if moved:
                logging.getLogger("tenants").info(
                    "[%s] секреты перенесены из JSON в хранилище: %s", slug, ", ".join(moved))
            self._cache[slug] = tenant
        return self._cache[slug]

    def list(self) -> list[dict]:
        out = []
        for slug in self.slugs():
            t = self.get(slug)
            out.append({
                "slug": slug,
                "title": t.title,
                "timezone": t.timezone,
                "services": len(t.services),
                "masters": len(t.masters),
                "aiEnabled": bool(t.ai.get("enabled")),
                "calendarMode": t.integration.get("mode", "local"),
                "channel": t.channel.get("kind", "web"),
            })
        return out

    def create(self, slug: str, title: str, *, copy_from: str | None = None) -> Tenant:
        slug = (slug or "").strip().lower()
        if not SLUG_RE.match(slug):
            raise TenantError("Код бизнеса: латиница, цифры и дефис, 3–40 символов")
        if self.exists(slug):
            raise TenantError(f"Бизнес «{slug}» уже существует")

        target = TENANTS_DIR / slug
        target.mkdir(parents=True, exist_ok=True)

        if copy_from:
            source = self.get(copy_from)
            salon = json.loads(json.dumps(source.salon))
            integration = json.loads(json.dumps(source.integration))
            # Секреты и чужие календари копировать нельзя — это другой бизнес.
            integration["mode"] = "local"
            for key in ("clientId", "clientSecret", "refreshToken", "serviceAccountFile", "impersonateUser"):
                integration.pop(key, None)
            integration.get("ai", {}).pop("apiKey", None)
            integration.pop("database", None)  # база общая на сервис, копировать нечего
            for key in ("whatsappToken", "whatsappVerifyToken", "whatsappPhoneId"):
                integration.get("channel", {}).pop(key, None)
            integration.get("handoff", {}).pop("telegramBotToken", None)
            for master in salon.get("masters", []):
                master["calendarId"] = "primary"
        else:
            salon = json.loads(json.dumps(DEFAULT_SALON))
            integration = json.loads(json.dumps(DEFAULT_INTEGRATION))

        salon["name"] = title or salon.get("name") or slug
        _write_json(target / "salon.json", salon)
        _write_json(target / "integration.json", integration)
        self._cache.pop(slug, None)
        return self.get(slug)

    def delete(self, slug: str) -> None:
        if not self.exists(slug):
            raise TenantError(f"Бизнес «{slug}» не найден")
        if len(self.slugs()) == 1:
            raise TenantError("Нельзя удалить единственный бизнес")
        shutil.rmtree(TENANTS_DIR / slug)
        if _secrets is not None:
            _secrets.drop(slug)  # чужие ключи не должны пережить бизнес
        self._cache.pop(slug, None)

    def invalidate(self, slug: str) -> None:
        self._cache.pop(slug, None)


registry = TenantRegistry()


def ensure_default_tenant(slug: str = "demo-salon", title: str = "Demo Salon") -> str | None:
    """Пустой том с бизнесами — поднимаем один по умолчанию, а не падаем.

    В Coolify tenants/ — это volume: при первом деплое он пуст, и без бизнеса
    виджет отвечал бы 503 вместо того, чтобы дать себя настроить.
    """
    if registry.slugs():
        return None
    registry.create(slug, title)
    return slug
