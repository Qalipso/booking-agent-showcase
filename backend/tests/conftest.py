"""Изолированное окружение.

Каждый тест получает свою папку tenants/ и свою БД — файлы проекта не трогаются
ни при каких обстоятельствах.
"""

from __future__ import annotations

import copy
import json
from datetime import timedelta

import pytest

from backend.app.calendar_service import CalendarService
from backend.app.db import Store
from backend.app.policies import RateLimiter
from backend.app.timeutil import now
from backend.app.tools import BookingTools, ToolContext

SALON = {
    "name": "Demo Salon",
    "tagline": "Hair · Color · Atmosphere",
    "address": "Кордон, Монтевидео",
    "whatsapp": "",
    "instagram": "",
    "timezone": "America/Montevideo",
    # Как у настоящего салона: по коду страны «092…» и «+598 92…» сходятся
    # в одного клиента, а не в две карточки.
    "phoneCountry": "598",
    "workHours": {"start": "11:00", "end": "20:00"},
    "workDays": [0, 1, 2, 3, 4, 5, 6],
    "slotStepMinutes": 30,
    "bookingHorizonDays": 14,
    "leadTimeMinutes": 60,
    "services": [
        {"id": "haircut", "title": "Стрижка", "duration": 60, "price": "от 900 UYU", "desc": ""},
        {"id": "color", "title": "Окрашивание", "duration": 150, "price": "", "desc": ""},
    ],
    "masters": [
        {"id": "alex", "name": "Alex", "role": "Hair and color",
         "services": ["haircut", "color"], "workDays": [0, 1, 2, 3, 4, 5, 6], "calendarId": "primary"},
        {"id": "taylor", "name": "Taylor", "role": "Стрижка",
         "services": ["haircut"], "workDays": [0, 1, 2, 3, 4, 5, 6], "calendarId": "primary"},
    ],
}

INTEGRATION = {
    "mode": "local",
    "secretManager": False,
    "ai": {"enabled": False, "provider": "openai", "model": "gpt-4.1-mini",
           "maxSteps": 8, "timeoutSeconds": 30, "language": "ru"},
    "channel": {"kind": "web", "allowedOrigins": ""},
    "policies": {
        "requireExplicitConfirmation": True, "recheckSlotBeforeInsert": True,
        "idempotencyEnabled": True, "allowCancel": True, "allowReschedule": False,
        "maxBookingsPerPhonePerDay": 3, "rateLimitPerMinute": 20,
        "maskPiiInLogs": True, "dataRetentionDays": 180,
    },
    "handoff": {"adminName": "Alex", "adminWhatsapp": "+598 99000101",
                "escalateOnCalendarError": True, "escalateOnUnknownIntent": True,
                "handoffMessage": "Передаю администратору."},
    # console — ничего не отправляем наружу, но весь сценарий очереди отрабатывает.
    "notifications": {
        "enabled": True, "provider": "console", "clientChannel": "whatsapp", "smsFallback": True,
        "ownerProvider": "console", "ownerPhone": "+598 99000101",
        "dayBeforeAt": "19:00", "sameDayHours": 3, "sameDayNotBefore": "09:00",
    },
}


@pytest.fixture(autouse=True)
def billing_plan(tmp_path, monkeypatch):
    """Тесты не должны упираться в лимиты тарифа и трогать боевой account.json."""
    from backend.app import billing

    monkeypatch.setattr(billing, "ACCOUNT_FILE", tmp_path / "account.json")
    monkeypatch.setattr(billing.account, "data", {**billing.DEFAULT_ACCOUNT, "plan": "agency"})
    return billing.account


@pytest.fixture(autouse=True)
def public_base_url(monkeypatch):
    """Публичный адрес сервиса — как на проде.

    Без него ссылки на оценку визита и на место из листа ожидания не строятся,
    а сообщения без ссылки не отправляются вовсе: отвечать «5» в WhatsApp
    некому. Тесты должны идти по тому же пути, что и прод, а не по ветке
    «переменная не задана».
    """
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://booking.test")


@pytest.fixture
def tenants_dir(tmp_path, monkeypatch):
    """Подменяем каталог бизнесов на временный — до создания любых объектов."""
    from backend.app import tenants as tenants_module

    target = tmp_path / "tenants"
    target.mkdir()
    monkeypatch.setattr(tenants_module, "TENANTS_DIR", target)
    monkeypatch.setattr(tenants_module.registry, "_cache", {})
    return target


def write_tenant(tenants_dir, slug: str, salon: dict | None = None, integration: dict | None = None):
    folder = tenants_dir / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "salon.json").write_text(
        json.dumps(salon or copy.deepcopy(SALON), ensure_ascii=False), encoding="utf-8")
    (folder / "integration.json").write_text(
        json.dumps(integration or copy.deepcopy(INTEGRATION), ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def tenant(tenants_dir):
    from backend.app.tenants import Tenant

    write_tenant(tenants_dir, "demo-salon")
    return Tenant("demo-salon")


# Прежнее имя фикстуры — в тестах читается как «настройки бизнеса».
@pytest.fixture
def settings(tenant):
    return tenant


@pytest.fixture
def store(tmp_path) -> Store:
    """Своя база на тест — и она же источник секретов для конфигурации бизнеса."""
    from backend.app.secretstore import SecretStore
    from backend.app.tenants import bind_secret_store

    db = Store(f"sqlite:///{tmp_path/'test.db'}")
    bind_secret_store(SecretStore(db))
    return db


@pytest.fixture
def notifications(store):
    from backend.app.notify import NotificationService

    return NotificationService(store)


@pytest.fixture
def tools(tenant, store, notifications) -> BookingTools:
    return BookingTools(tenant, store, CalendarService(tenant, store), RateLimiter(), notifications)


@pytest.fixture
def tomorrow(tenant) -> str:
    return (now(tenant.timezone) + timedelta(days=1)).date().isoformat()


@pytest.fixture
def confirmed_ctx() -> ToolContext:
    return ToolContext(conversation_id="conv-test",
                       history=[{"role": "user", "content": "да, подтверждаю"}])


@pytest.fixture
def client(tenants_dir, tmp_path, monkeypatch):
    """HTTP-клиент на временных файлах и временной БД."""
    from fastapi.testclient import TestClient

    from backend.app import deps
    from backend.app.db import Store

    write_tenant(tenants_dir, "demo-salon")
    monkeypatch.setenv("ADMIN_ALLOW_NO_TOKEN", "1")  # админка без токена — только в тестах
    # Подключаем временную БД: боевую тесты не трогают ни при каких обстоятельствах.
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'api.db'}"))

    from backend.app.main import app

    return TestClient(app)


@pytest.fixture
def client_google(client, tmp_path):
    """HTTP-клиент, у которого календарь работает через подставной Google."""
    from backend.app import deps
    from backend.tests.test_google import FakeClient

    events: dict = {}
    rt = deps.runtime.for_tenant("demo-salon")
    rt.calendar._client = FakeClient(events)   # noqa: SLF001 — подмена транспорта
    rt.calendar.mode = "google"
    return client, events


@pytest.fixture
def client_google_forbidden(client):
    """Доступ выдан, но календарь мастера не расшарен — самый частый отказ."""
    from backend.app import deps
    from backend.tests.test_google import FakeClient

    rt = deps.runtime.for_tenant("demo-salon")
    rt.calendar._client = FakeClient({}, fail="Forbidden: writer access required")  # noqa: SLF001
    rt.calendar.mode = "google"
    return client
