"""Бизнес-логика: тариф и лимиты, неявки, эскалация менеджеру, статистика, диалоги."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app import billing
from backend.app.tools import ToolContext, ToolError
from backend.tests.conftest import write_tenant


def first_slot(tools, tomorrow, service_id="haircut", master_id="alex"):
    data = tools.get_free_slots(service_id=service_id, master_id=master_id, date_from=tomorrow, days=1)
    return data["availability"][0]["days"][0]["slots"]


def book(tools, slot, ctx, *, name="Jordan", phone="+598 91234567"):
    return tools.create_booking(
        service_id="haircut", master_id="alex", start=slot["start"], customer_name=name,
        phone=phone, confirmation_token=slot["token"], ctx=ctx,
    )


# --- тариф и лимиты ----------------------------------------------------------

def test_booking_counts_against_plan(tools, tomorrow, confirmed_ctx, store, tenant):
    slots = first_slot(tools, tomorrow)
    book(tools, slots[0], confirmed_ctx)
    usage = store.usage(billing.period_key())
    assert usage.get("bookings") == 1


def test_booking_limit_blocks_and_escalates(tools, tomorrow, confirmed_ctx, monkeypatch):
    """Лимит тарифа исчерпан — запись не создаётся, владелец получает эскалацию."""
    monkeypatch.setattr(billing.account, "data", {**billing.DEFAULT_ACCOUNT, "plan": "trial"})
    monkeypatch.setitem(billing.PLANS["trial"]["limits"], "bookings", 1)

    slots = first_slot(tools, tomorrow)
    book(tools, slots[0], confirmed_ctx)
    with pytest.raises(ToolError, match="лимит записей"):
        book(tools, slots[2], confirmed_ctx, phone="+598 99999999")


def test_cancelled_subscription_stops_bookings(tools, tomorrow, confirmed_ctx, monkeypatch):
    monkeypatch.setattr(billing.account, "data",
                        {**billing.DEFAULT_ACCOUNT, "plan": "solo", "status": "cancelled"})
    slots = first_slot(tools, tomorrow)
    with pytest.raises(ToolError, match="Подписка приостановлена"):
        book(tools, slots[0], confirmed_ctx)


def test_tenant_limit_by_plan(monkeypatch):
    monkeypatch.setattr(billing.account, "data", {**billing.DEFAULT_ACCOUNT, "plan": "solo"})
    billing.check_can_add_tenant(0)                      # первый бизнес — можно
    with pytest.raises(billing.LimitExceeded, match="рассчитан на 1"):
        billing.check_can_add_tenant(1)                  # второй — нет


# --- неявки ------------------------------------------------------------------

def test_third_no_show_requires_confirmation(tools, tomorrow, confirmed_ctx, store, tenant):
    """Три неявки — следующая запись создаётся с требованием подтвердить визит."""
    phone = "+598 91111111"
    slots = first_slot(tools, tomorrow)
    normalized = "59891111111"
    for i in range(3):
        booking = store.create_booking(
            tenant_id=tenant.slug, master_id="taylor", service_id="haircut",
            start_at=datetime.now(timezone.utc) - timedelta(days=10 + i),
            end_at=datetime.now(timezone.utc) - timedelta(days=10 + i) + timedelta(hours=1),
            client_name="Тест", phone=normalized,
        )
        store.set_booking_status(booking.id, "no_show", tenant_id=tenant.slug)

    fresh = book(tools, slots[0], confirmed_ctx, phone=phone)
    stored = store.get_booking(fresh["booking_id"], tenant_id=tenant.slug)
    assert stored.requires_confirmation is True


def test_two_no_shows_are_not_flagged(tools, tomorrow, confirmed_ctx, store, tenant):
    phone, normalized = "+598 92222222", "59892222222"
    for i in range(2):
        booking = store.create_booking(
            tenant_id=tenant.slug, master_id="taylor", service_id="haircut",
            start_at=datetime.now(timezone.utc) - timedelta(days=5 + i),
            end_at=datetime.now(timezone.utc) - timedelta(days=5 + i) + timedelta(hours=1),
            client_name="Тест", phone=normalized,
        )
        store.set_booking_status(booking.id, "no_show", tenant_id=tenant.slug)

    fresh = book(tools, first_slot(tools, tomorrow)[0], confirmed_ctx, phone=phone)
    stored = store.get_booking(fresh["booking_id"], tenant_id=tenant.slug)
    assert stored.requires_confirmation is False


def test_old_no_shows_fall_out_of_window(tools, tomorrow, confirmed_ctx, store, tenant):
    """Неявки годичной давности не должны портить репутацию клиента навсегда."""
    tenant.integration["policies"]["noShowWindowDays"] = 30
    phone, normalized = "+598 93333333", "59893333333"
    for i in range(4):
        booking = store.create_booking(
            tenant_id=tenant.slug, master_id="taylor", service_id="haircut",
            start_at=datetime.now(timezone.utc) - timedelta(days=200 + i),
            end_at=datetime.now(timezone.utc) - timedelta(days=200 + i) + timedelta(hours=1),
            client_name="Тест", phone=normalized,
        )
        store.set_booking_status(booking.id, "no_show", tenant_id=tenant.slug)

    fresh = book(tools, first_slot(tools, tomorrow)[0], confirmed_ctx, phone=phone)
    assert store.get_booking(fresh["booking_id"], tenant_id=tenant.slug).requires_confirmation is False


# --- эскалация менеджеру -----------------------------------------------------

def test_handoff_writes_to_manager_whatsapp(tools, tenant, monkeypatch):
    tenant.integration["handoff"]["managerWhatsapp"] = "+598 95555555"
    sent = {}

    def fake_send(**kwargs):
        sent.update(kwargs)
        from backend.app.notify.providers import SendResult

        return SendResult(status="sent", provider_message_id="x")

    monkeypatch.setattr("backend.app.notify.providers.send", fake_send)

    result = tools.handoff_to_human(reason="Клиент жалуется на цвет",
                                    summary="Хочет переделку", ctx=ToolContext("c1", []))
    assert result["contact"] == "+598 95555555"
    assert sent["to"] == "+598 95555555"
    assert sent["channel"] == "whatsapp"
    assert "Клиент жалуется" in sent["body"]


def test_handoff_counts_in_usage(tools, store, tenant):
    tools.handoff_to_human(reason="Непонятный запрос", ctx=ToolContext("c1", []))
    assert store.usage(billing.period_key()).get("handoffs") == 1


# --- мягкая продажа ----------------------------------------------------------

def test_upsell_rules_in_prompt(tenant, tools):
    from backend.app.agent import build_system_prompt

    tenant.salon["services"][0]["suggestWith"] = ["color"]
    tenant.integration["sales"] = {"upsellEnabled": True, "upsellMaxPerDialog": 1,
                                   "upsellMoment": "after_booking", "fillGaps": True}
    prompt = build_system_prompt(tenant, tools)
    assert "ОДИН раз" in prompt
    assert "«Стрижка» — «Окрашивание»" in prompt
    assert "два ближайших свободных" in prompt


def test_upsell_can_be_disabled(tenant, tools):
    from backend.app.agent import build_system_prompt

    tenant.integration["sales"] = {"upsellEnabled": False, "fillGaps": False}
    prompt = build_system_prompt(tenant, tools)
    assert "Ничего не предлагай сверх" in prompt


# --- экраны владельца --------------------------------------------------------

@pytest.fixture
def client(tenants_dir, tmp_path, monkeypatch):
    from backend.app import deps
    from backend.app.db import Store

    write_tenant(tenants_dir, "demo-salon")
    monkeypatch.setenv("ADMIN_ALLOW_NO_TOKEN", "1")  # админка без токена — только в тестах
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'api.db'}"))

    from backend.app.main import app

    return TestClient(app)


def make_booking(client, tomorrow, *, phone="+598 91234567", index=0):
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    slot = slots[index]
    res = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slot["time"],
        "name": "Jordan", "phone": phone, "token": slot["token"],
    })
    assert res.status_code == 200, res.text
    return res.json()["bookingId"]


def test_status_endpoint_marks_no_show(client, tomorrow):
    booking_id = make_booking(client, tomorrow)
    res = client.post(f"/api/admin/bookings/{booking_id}/status", json={"status": "no_show"})
    assert res.status_code == 200
    assert res.json()["status"] == "no_show"
    assert res.json()["noShowCount"] == 1


def test_status_endpoint_rejects_unknown_status(client, tomorrow):
    booking_id = make_booking(client, tomorrow)
    assert client.post(f"/api/admin/bookings/{booking_id}/status",
                       json={"status": "пришёл"}).status_code == 422


def test_stats_counts_successful_and_cancelled(client, tomorrow):
    done = make_booking(client, tomorrow, index=0)
    lost = make_booking(client, tomorrow, index=2, phone="+598 92222222")
    client.post(f"/api/admin/bookings/{done}/status", json={"status": "completed"})
    client.post(f"/api/admin/bookings/{lost}/status", json={"status": "cancelled"})

    data = client.get("/api/admin/stats", params={"days": 30}).json()["stats"]
    assert data["bookings"] == 2
    assert data["completed"] == 1
    assert data["cancelled"] == 1
    assert data["successful"] == 1
    assert data["cancelledPct"] == 50.0


def test_schedule_shows_bookings_per_master(client, tomorrow):
    make_booking(client, tomorrow)
    data = client.get("/api/admin/schedule", params={"date": tomorrow}).json()
    alex = next(c for c in data["columns"] if c["masterId"] == "alex")
    taylor = next(c for c in data["columns"] if c["masterId"] == "taylor")
    assert len(alex["events"]) == 1
    assert alex["events"][0]["client"] == "Jordan"
    assert taylor["events"] == []


def test_conversations_list_and_detail(client, tomorrow):
    """Кнопочная запись тоже создаёт диалог — он должен быть виден в истории."""
    make_booking(client, tomorrow)
    listing = client.get("/api/admin/conversations").json()["conversations"]
    assert len(listing) == 1
    assert listing[0]["bookings"] == 1

    detail = client.get(f"/api/admin/conversations/{listing[0]['id']}").json()
    assert detail["bookings"][0]["client"] == "Jordan"


def test_conversation_detail_has_full_booking_facts(client, tomorrow):
    """Карточка записи в диалоге показывает всё — иначе владелец идёт в «Записи».

    Услуга и мастер — названиями, а не идентификаторами: в базе лежат коды,
    справочник живёт в конфигурации бизнеса.
    """
    make_booking(client, tomorrow)
    conv_id = client.get("/api/admin/conversations").json()["conversations"][0]["id"]
    b = client.get(f"/api/admin/conversations/{conv_id}").json()["bookings"][0]

    assert b["service"] == "Стрижка"
    assert b["master"] == "Alex"
    assert b["duration"] == 60
    assert b["phone"]
    assert b["end"] > b["start"]
    assert b["createdAt"]
    assert b["notifyConsent"] is True
    assert isinstance(b["notifications"], list)


def test_conversation_of_other_tenant_is_404(client, tomorrow):
    make_booking(client, tomorrow)
    conv_id = client.get("/api/admin/conversations").json()["conversations"][0]["id"]
    client.post("/api/admin/tenants", json={"slug": "second-demo", "title": "Barber"})
    res = client.get(f"/api/admin/conversations/{conv_id}", params={"tenant": "second-demo"})
    assert res.status_code == 404


def test_billing_endpoint_and_plan_change(client):
    body = client.get("/api/admin/billing").json()
    assert body["usage"]["tenants"]["used"] == 1

    changed = client.put("/api/admin/billing", json={"plan": "solo", "status": "active"})
    assert changed.status_code == 200
    assert changed.json()["plan"] == "solo"


def test_plan_downgrade_blocked_when_too_many_tenants(client):
    client.post("/api/admin/tenants", json={"slug": "second-demo", "title": "Barber"})
    client.post("/api/admin/tenants", json={"slug": "third-one", "title": "Third"})
    res = client.put("/api/admin/billing", json={"plan": "solo"})
    assert res.status_code == 422
    assert "допускает 1" in res.json()["detail"]


def test_tenant_creation_blocked_by_plan(client, monkeypatch):
    monkeypatch.setattr(billing.account, "data", {**billing.DEFAULT_ACCOUNT, "plan": "solo"})
    res = client.post("/api/admin/tenants", json={"slug": "second-demo", "title": "Barber"})
    assert res.status_code == 402
