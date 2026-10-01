"""Секреты живут в окружении сервера и в базе — но не в JSON-конфигурации.

Порядок разрешения одинаков для всех секретов:

1. переменная окружения бизнеса — ``DEMO_SALON_AI_API_KEY``;
2. глобальная переменная окружения — ``AI_API_KEY``;
3. таблица ``tenant_secrets`` — то, что владелец ввёл в админ-форме или что
   пришло из OAuth-колбэка.

JSON-файлы бизнесов секретов не содержат вовсе: они лежат в репозитории, а
репозиторий уезжает в GitHub. ``DATABASE_URL`` в этом списке нет намеренно: базой
нельзя настроить доступ к самой базе, поэтому она задаётся только окружением
сервера, а админка её лишь показывает.
"""

from __future__ import annotations

import os
import re

# Путь в integration.json → имя переменной окружения.
SECRET_ENV: dict[str, str] = {
    "clientSecret": "GOOGLE_CLIENT_SECRET",
    "refreshToken": "GOOGLE_REFRESH_TOKEN",
    "ai.apiKey": "AI_API_KEY",
    "channel.whatsappToken": "WHATSAPP_TOKEN",
    "channel.whatsappVerifyToken": "WHATSAPP_VERIFY_TOKEN",
    "handoff.telegramBotToken": "TELEGRAM_BOT_TOKEN",
    "notifications.twilioAccountSid": "TWILIO_ACCOUNT_SID",
    "notifications.twilioAuthToken": "TWILIO_AUTH_TOKEN",
    "notifications.smtpPassword": "SMTP_PASSWORD",
}

# Секреты, которые в базе не хранятся ни при каких условиях. Пусто: строку
# подключения к базе форма больше не предлагает вводить вовсе.
ENV_ONLY: set[str] = set()

SECRET_PATHS = frozenset(SECRET_ENV)


def env_name(path: str, slug: str = "") -> str:
    """`ai.apiKey` + `demo-salon` → `DEMO_SALON_AI_API_KEY`."""
    base = SECRET_ENV[path]
    if not slug:
        return base
    prefix = re.sub(r"[^A-Z0-9]+", "_", slug.upper()).strip("_")
    return f"{prefix}_{base}"


def from_env(path: str, slug: str = "") -> str:
    if path not in SECRET_ENV:
        return ""
    return (os.getenv(env_name(path, slug)) or os.getenv(SECRET_ENV[path]) or "").strip()


class SecretStore:
    """Секреты, введённые через админ-форму. Хранятся в базе, не в файлах."""

    def __init__(self, store) -> None:
        self._store = store

    def get(self, slug: str, path: str) -> str:
        value = from_env(path, slug)
        if value or path in ENV_ONLY:
            return value
        return self._store.get_secret(slug, path)

    def set(self, slug: str, path: str, value: str) -> None:
        if path in ENV_ONLY:
            return  # DATABASE_URL задаётся только окружением
        self._store.set_secret(slug, path, value)

    def has(self, slug: str, path: str) -> bool:
        return bool(self.get(slug, path))

    def drop(self, slug: str) -> None:
        self._store.drop_secrets(slug)
