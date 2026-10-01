"""Загрузка и сохранение конфигурации. Единственное место, которое трогает config/."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from .schema import CONFIG_DIR, ROOT, to_env, to_files, to_form, validate_config

SALON_FILE = CONFIG_DIR / "salon.json"
INTEGRATION_FILE = CONFIG_DIR / "integration.json"
ENV_FILE = ROOT / ".env.generated"

_lock = threading.Lock()


def _read_json(path: Path, fallback: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(fallback)


class Settings:
    """Конфигурация в памяти. Перечитывается при сохранении формы."""

    def __init__(self) -> None:
        self.salon = _read_json(SALON_FILE, {})
        self.integration = _read_json(INTEGRATION_FILE, {"mode": "local"})

    # --- удобные срезы ----------------------------------------------------
    @property
    def timezone(self) -> str:
        return self.salon.get("timezone", "UTC")

    @property
    def services(self) -> list[dict]:
        return self.salon.get("services", [])

    @property
    def masters(self) -> list[dict]:
        return self.salon.get("masters", [])

    @property
    def ai(self) -> dict:
        return self.integration.get("ai", {})

    @property
    def channel(self) -> dict:
        return self.integration.get("channel", {"kind": "web"})

    @property
    def policies(self) -> dict:
        return self.integration.get("policies", {})

    @property
    def handoff(self) -> dict:
        return self.integration.get("handoff", {})

    def service(self, service_id: str) -> dict | None:
        return next((s for s in self.services if s["id"] == service_id), None)

    def master(self, master_id: str) -> dict | None:
        return next((m for m in self.masters if m["id"] == master_id), None)

    def policy(self, key: str, default: Any = None) -> Any:
        return self.policies.get(key, default)

    # --- форма ------------------------------------------------------------
    def form_data(self) -> dict:
        return to_form(self.salon, self.integration)

    def env_preview(self) -> str:
        return to_env(self.integration)

    def save_form(self, data: dict) -> tuple[bool, list[str]]:
        errors = validate_config(data)
        if errors:
            return False, errors

        salon, integration = to_files(data, self.integration)
        with _lock:
            # Пишем через временный файл: половинчатый конфиг сломал бы бота.
            for path, value in ((SALON_FILE, salon), (INTEGRATION_FILE, integration)):
                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                tmp.replace(path)
            ENV_FILE.write_text(to_env(integration), encoding="utf-8")
            self.salon, self.integration = salon, integration
        return True, []


settings = Settings()


def admin_token() -> str | None:
    return (os.getenv("ADMIN_TOKEN") or "").strip() or None


def admin_open() -> bool:
    """Админка без токена допустима только явным разрешением для локальной разработки.

    Без этого одна забытая переменная окружения отдаёт настройки, ключи и список
    записей любому, кто знает URL.
    """
    return os.getenv("ADMIN_ALLOW_NO_TOKEN") == "1"
