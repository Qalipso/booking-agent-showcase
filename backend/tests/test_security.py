"""Защита контура: админ-токен, CORS, маскирование PII, секреты вне файлов."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from backend.app import main as main_module
from backend.app.db import Store
from backend.app.policies import install_pii_filter
from backend.tests.conftest import write_tenant

TOKEN = "test-admin-token"


@pytest.fixture
def secured_client(tenants_dir, tmp_path, monkeypatch):
    from backend.app import deps

    write_tenant(tenants_dir, "demo-salon")
    monkeypatch.setenv("ADMIN_TOKEN", TOKEN)
    monkeypatch.delenv("ADMIN_ALLOW_NO_TOKEN", raising=False)
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'sec.db'}"))
    return TestClient(main_module.app)


def test_admin_requires_token(secured_client):
    assert secured_client.get("/api/admin/config").status_code == 401
    assert secured_client.get("/api/admin/config", headers={"X-Admin-Token": TOKEN}).status_code == 200


def test_admin_rejects_wrong_token(secured_client):
    assert secured_client.get("/api/admin/config",
                              headers={"X-Admin-Token": "test-admin-tokeN"}).status_code == 401


def test_admin_is_closed_without_token_in_environment(tenants_dir, tmp_path, monkeypatch):
    """Забытая переменная окружения не должна открывать настройки всему интернету.

    Отвечаем 401, а не 503: с появлением входа по паролю отсутствие ADMIN_TOKEN
    больше не значит «админка отключена» — значит «предъявите себя». Настройки
    при этом закрыты так же наглухо.
    """
    from backend.app import deps

    write_tenant(tenants_dir, "demo-salon")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_ALLOW_NO_TOKEN", raising=False)
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'noadmin.db'}"))

    assert TestClient(main_module.app).get("/api/admin/config").status_code == 401


def test_admin_brute_force_is_rate_limited(secured_client):
    from backend.app.routers import admin as admin_router

    admin_router._attempts._hits.clear()
    codes = [secured_client.get("/api/admin/config", headers={"X-Admin-Token": f"x{i}"}).status_code
             for i in range(15)]
    assert 429 in codes


def test_cors_allows_only_configured_origin(tenants_dir, monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://demo-salon.vercel.app")
    assert main_module.allowed_origins() == ["https://demo-salon.vercel.app"]


def test_cors_falls_back_to_demo_salon_not_to_wildcard(tenants_dir, monkeypatch):
    """Пустая настройка — это домен Demo Salon, а не «разрешено всем»."""
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOW_ALL", raising=False)
    write_tenant(tenants_dir, "demo-salon")
    assert main_module.allowed_origins() == list(main_module.DEFAULT_ORIGINS)
    assert "*" not in main_module.allowed_origins()


def test_pii_is_masked_even_when_phone_is_an_argument():
    """Телефон обычно приходит через %s — правки одного шаблона тут мало."""
    from backend.app.policies import PiiFilter

    record = logging.getLogger("notify").makeRecord(
        "notify", logging.INFO, __file__, 1, "whatsapp → %s: текст", ("+598 91234567",), None)
    PiiFilter(True).filter(record)
    assert "91234567" not in record.getMessage()
    assert "+***" in record.getMessage()


def test_pii_filter_is_installed_on_handlers_not_loggers():
    """На логгере фильтр не увидел бы записи дочерних `notify` и `worker`."""
    from backend.app.policies import PiiFilter

    install_pii_filter(True)
    handlers = logging.getLogger().handlers
    assert handlers
    assert all(any(isinstance(f, PiiFilter) for f in h.filters) for h in handlers)


def test_tenant_files_contain_no_secrets(tenants_dir, tmp_path, monkeypatch):
    """После сохранения формы токен лежит в базе, а не в JSON под git."""
    from backend.app import deps
    from backend.app.tenants import Tenant

    write_tenant(tenants_dir, "demo-salon")
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'secrets.db'}"))

    tenant = Tenant("demo-salon")
    form = tenant.form_data()
    form["handoff"] = {**form["handoff"], "telegramBotToken": "живой-токен"}
    ok, errors = tenant.save_form(form)
    assert ok, errors

    on_disk = (tenants_dir / "demo-salon" / "integration.json").read_text(encoding="utf-8")
    assert "живой-токен" not in on_disk
    assert json.loads(on_disk)["handoff"].get("telegramBotToken") is None
    assert tenant.handoff["telegramBotToken"] == "живой-токен"  # рантайм его видит


def test_environment_secret_wins_over_stored_one(tenants_dir, tmp_path, monkeypatch):
    from backend.app import deps
    from backend.app.tenants import Tenant

    write_tenant(tenants_dir, "demo-salon")
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'env.db'}"))
    deps.runtime.secrets.set("demo-salon", "handoff.telegramBotToken", "из-базы")

    monkeypatch.setenv("DEMO_SALON_TELEGRAM_BOT_TOKEN", "из-окружения")
    assert Tenant("demo-salon").handoff["telegramBotToken"] == "из-окружения"


def test_security_headers_on_every_response(secured_client):
    headers = secured_client.get("/health").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Content-Security-Policy"] == "frame-ancestors 'none'"
    assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_hsts_only_behind_https(secured_client):
    # На http HSTS загнал бы локальную разработку в вечный редирект на https.
    assert "Strict-Transport-Security" not in secured_client.get("/health").headers
    behind_proxy = secured_client.get("/health", headers={"X-Forwarded-Proto": "https"})
    assert "max-age=31536000" in behind_proxy.headers["Strict-Transport-Security"]


def test_telegram_webhook_rejects_wrong_signature(secured_client):
    """Адрес вебхука публичный — пускать по нему может только подпись.

    Без неё любой, угадав адрес, отмечал бы чужие записи «не пришёл».
    """
    res = secured_client.post("/api/telegram/demo-salon/webhook",
                              json={"message": {"text": "/today", "chat": {"id": "1"}}},
                              headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"})
    assert res.status_code == 403


def test_telegram_webhook_accepts_valid_signature(secured_client):
    from backend.app.policies import webhook_secret

    res = secured_client.post("/api/telegram/demo-salon/webhook",
                              json={"message": {"text": "/today", "chat": {"id": "1"}}},
                              headers={"X-Telegram-Bot-Api-Secret-Token": webhook_secret("demo-salon")})
    # Бот не подключён — апдейт молча принимается, а не падает.
    assert res.status_code == 200


def test_telegram_webhook_unknown_tenant_is_404(secured_client):
    from backend.app.policies import webhook_secret

    res = secured_client.post("/api/telegram/нет-такого/webhook", json={},
                              headers={"X-Telegram-Bot-Api-Secret-Token": webhook_secret("нет-такого")})
    assert res.status_code == 404
