"""Путь Google Calendar: OAuth, режимы календаря и круговая проверка связи.

Настоящий Google здесь не дёргается — подменяются HTTP-слой и клиент API.
Проверяется то, что ломается на живом подключении: обмен кода на токен,
хранение refresh token вне файлов, деградация вместо тихого демо-режима и
понятные подсказки вместо англоязычных ошибок Google.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app import google_oauth
from backend.app.calendar_service import CalendarError, CalendarService, calendar_id


# --- заглушки Google ----------------------------------------------------------

class FakeResponse:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status
        self.is_success = status < 400
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if not self.is_success:
            import httpx
            raise httpx.HTTPStatusError("ошибка", request=None, response=None)


class FakeEvents:
    """Календарь Google в памяти: события создаются и удаляются по-настоящему."""

    def __init__(self, store: dict, fail: str = "") -> None:
        self.store = store
        self.fail = fail

    def insert(self, *, calendarId, body):  # noqa: N803 — сигнатура Google API
        events, fail = self.store, self.fail

        class Call:
            def execute(self):
                if fail:
                    raise RuntimeError(fail)
                event_id = f"evt-{len(events) + 1}"
                events[event_id] = {"calendarId": calendarId, **body}
                return {"id": event_id, "htmlLink": f"https://calendar.google.com/{event_id}"}
        return Call()

    def delete(self, *, calendarId, eventId):  # noqa: N803
        events, fail = self.store, self.fail

        class Call:
            def execute(self):
                if fail:
                    raise RuntimeError(fail)
                events.pop(eventId, None)
                return {}
        return Call()


class FakeClient:
    def __init__(self, events: dict, fail: str = "") -> None:
        self._events = FakeEvents(events, fail)

    def events(self):
        return self._events


@pytest.fixture
def google_calendar(tenant, store):
    """Календарь в режиме Google с подставным клиентом."""
    events: dict = {}
    service = CalendarService(tenant, store)
    service._client = FakeClient(events)   # noqa: SLF001 — подмена транспорта в тесте
    service.mode = "google"
    return service, events


# --- OAuth --------------------------------------------------------------------

def test_auth_url_asks_for_refresh_token(tenant, store, monkeypatch):
    """Без access_type=offline и prompt=consent Google не выдаст refresh token."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")

    url = google_oauth.build_auth_url(tenant, "https://booking.example.com/api/admin/google/callback")
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "client_id=client-id" in url
    assert "calendar" in url


def test_state_is_single_use_and_expires(tenant, monkeypatch):
    """Чужой или повторно использованный state не должен открывать подключение."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")

    url = google_oauth.build_auth_url(tenant, "https://example.com/cb")
    state = url.split("state=")[1].split("&")[0]

    assert google_oauth.consume_state(state).tenant == tenant.slug
    with pytest.raises(google_oauth.OAuthError):
        google_oauth.consume_state(state)          # второй раз — уже нельзя
    with pytest.raises(google_oauth.OAuthError):
        google_oauth.consume_state("подделка")


def test_exchange_code_returns_refresh_token(tenant, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(google_oauth.httpx, "post",
                        lambda *a, **k: FakeResponse({"refresh_token": "1//refresh", "access_token": "ya29"}))
    monkeypatch.setattr(google_oauth.httpx, "get",
                        lambda *a, **k: FakeResponse({"email": "salon@example.com"}))

    result = google_oauth.exchange_code(tenant, "code-123", "https://example.com/cb")
    assert result == {"refresh_token": "1//refresh", "email": "salon@example.com"}


def test_missing_refresh_token_is_explained(tenant, monkeypatch):
    """Google молча отдаёт доступ без refresh token, если согласие уже давали."""
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(google_oauth.httpx, "post",
                        lambda *a, **k: FakeResponse({"access_token": "ya29"}))

    with pytest.raises(google_oauth.OAuthError) as exc:
        google_oauth.exchange_code(tenant, "code", "https://example.com/cb")
    assert "myaccount.google.com/permissions" in str(exc.value)


def test_refresh_token_goes_to_secret_store_not_to_file(tenant, tenants_dir, store):
    """Токен доступа к календарю не должен оказаться в JSON под git."""
    import json

    from backend.app.secretstore import SecretStore
    from backend.app.tenants import bind_secret_store

    bind_secret_store(SecretStore(store))
    tenant.patch_integration({"mode": "oauth", "refreshToken": "1//секрет",
                              "googleAccount": "salon@example.com"})

    on_disk = json.loads((tenants_dir / tenant.slug / "integration.json").read_text(encoding="utf-8"))
    assert "1//секрет" not in json.dumps(on_disk, ensure_ascii=False)
    assert on_disk.get("googleAccount") == "salon@example.com"   # не секрет, остаётся в файле
    assert tenant.google["refreshToken"] == "1//секрет"          # рантайм его видит


# --- режимы календаря ---------------------------------------------------------

def test_local_mode_does_not_pretend_to_be_broken(tenant, store):
    """Календарь не настраивали — это не поломка, тревожить владельца нечем."""
    service = CalendarService(tenant, store)
    assert service.mode == "local"
    assert service.degraded is False


def test_configured_but_unusable_calendar_is_degraded_not_local(tenant, store):
    """Настроен OAuth без токена: демо-режимом это притворяться не должно."""
    tenant.integration["mode"] = "oauth"
    service = CalendarService(tenant, store)

    assert service.mode == "local"      # писать в календарь всё равно нечем
    assert service.degraded is True     # но владельцу видно, что интеграция сломана
    assert "refresh token" in service.error


def test_master_without_calendar_id_falls_back_to_primary():
    assert calendar_id({"id": "alex"}) == "primary"
    assert calendar_id({"id": "alex", "calendarId": ""}) == "primary"
    assert calendar_id({"id": "alex", "calendarId": " team@group.calendar.google.com "}) \
        == "team@group.calendar.google.com"


# --- запись в календарь -------------------------------------------------------

def test_event_carries_client_and_tenant(tenant, google_calendar):
    service, events = google_calendar
    start = datetime.now(timezone.utc) + timedelta(days=1)

    event = service.create_event(
        master=tenant.masters[0], service=tenant.services[0],
        start=start, end=start + timedelta(hours=1),
        client_name="Мария", phone="+598 99123456", comment="колорист",
    )

    stored = events[event["id"]]
    assert "Мария" in stored["summary"]
    assert "+598 99123456" in stored["description"]
    assert stored["extendedProperties"]["private"]["tenantId"] == tenant.slug
    assert stored["start"]["timeZone"] == tenant.timezone


def test_calendar_failure_is_not_swallowed(tenant, store):
    """Отказ календаря обязан всплыть: иначе клиенту скажут «вы записаны» зря."""
    service = CalendarService(tenant, store)
    service._client = FakeClient({}, fail="Forbidden")   # noqa: SLF001
    service.mode = "google"
    start = datetime.now(timezone.utc) + timedelta(days=1)

    with pytest.raises(CalendarError):
        service.create_event(master=tenant.masters[0], service=tenant.services[0],
                             start=start, end=start + timedelta(hours=1),
                             client_name="Мария", phone="598991234")


# --- круговая проверка связи --------------------------------------------------

def test_verify_creates_and_removes_probe_event(client_google):
    """Проверка не должна оставлять мусор в календаре салона."""
    client, events = client_google
    res = client.post("/api/admin/google/verify")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert {m["master"] for m in body["masters"]} == {"Alex", "Taylor"}
    assert events == {}, "тестовое событие должно быть удалено"


def test_verify_explains_missing_access(client_google_forbidden):
    """Английский текст Google бесполезен владельцу салона — нужен совет."""
    res = client_google_forbidden.post("/api/admin/google/verify")

    body = res.json()
    assert body["ok"] is False
    assert all(not m["ok"] for m in body["masters"])
    assert "Внесение изменений" in body["masters"][0]["detail"]


def test_verify_refuses_when_calendar_is_not_connected(client):
    """Без подключения проверять нечего — 409 с причиной, а не ложное «ок»."""
    assert client.post("/api/admin/google/verify").status_code == 409
