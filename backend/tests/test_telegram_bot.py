"""Входящие Telegram: кто спрашивает, что ему видно и что он может изменить."""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.app import auth, telegram, telegram_bot
from backend.app.policies import master_link_code, user_link_code, webhook_secret


@pytest.fixture
def sent(monkeypatch):
    """Перехват исходящих: наружу в тестах ничего не уходит."""
    out = {"messages": [], "answers": [], "markup": []}
    monkeypatch.setattr(telegram, "send",
                        lambda token, chat, text, buttons=None: out["messages"].append((chat, text, buttons)))
    monkeypatch.setattr(telegram, "answer_callback",
                        lambda token, cid, text="": out["answers"].append(text))
    monkeypatch.setattr(telegram, "edit_markup",
                        lambda token, chat, mid, buttons=None: out["markup"].append(mid))
    return out


def message(text, chat_id):
    return {"message": {"text": text, "chat": {"id": chat_id}}}


def press(status, booking_id, chat_id, message_id=77):
    return {"callback_query": {"id": "cb1", "data": f"b:{status}:{booking_id}",
                               "message": {"message_id": message_id, "chat": {"id": chat_id}}}}


def test_stranger_gets_no_answer(tenant, store, sent):
    """Бот салона не отвечает посторонним — даже отказом.

    Ответ «вы не сотрудник» подтверждал бы чужому, что бот живой и чей он.
    """
    telegram_bot.handle_update(message("/today", "999999"), tenant, store, "t")
    assert sent["messages"] == []


def test_master_sees_only_his_own_day(tools, tenant, store, tomorrow, confirmed_ctx, sent):
    tenant.salon["masters"][0]["telegramChatId"] = "111"      # alex
    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    tools.create_booking(service_id="haircut", master_id="alex", start=slot["start"],
                         customer_name="Клиент Alex", phone="+598 91234567",
                         confirmation_token=slot["token"], ctx=confirmed_ctx)
    taylor = tools.get_free_slots(service_id="haircut", master_id="taylor", date_from=tomorrow)
    nslot = taylor["availability"][0]["days"][0]["slots"][0]
    tools.create_booking(service_id="haircut", master_id="taylor", start=nslot["start"],
                         customer_name="Клиент Нины", phone="+598 99999999",
                         confirmation_token=nslot["token"], ctx=confirmed_ctx)

    telegram_bot.handle_update(message("/tomorrow", "111"), tenant, store, "t")
    text = sent["messages"][-1][1]
    assert "Клиент Alex" in text
    assert "Клиент Нины" not in text


def test_button_marks_the_visit(tools, tenant, store, tomorrow, confirmed_ctx, sent):
    tenant.salon["masters"][0]["telegramChatId"] = "111"
    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(service_id="haircut", master_id="alex", start=slot["start"],
                                customer_name="Jordan", phone="+598 91234567",
                                confirmation_token=slot["token"], ctx=confirmed_ctx)

    telegram_bot.handle_update(press("completed", made["booking_id"], "111"), tenant, store, "t")
    assert store.get_booking(made["booking_id"], tenant_id=tenant.slug).status == "completed"
    assert "пришёл" in sent["answers"][0]
    assert sent["markup"] == [77]   # кнопки убраны, второй раз не нажать


def test_master_cannot_touch_another_masters_booking(
        tools, tenant, store, tomorrow, confirmed_ctx, sent):
    """Знание чужого id не должно давать власти над чужой записью."""
    tenant.salon["masters"][0]["telegramChatId"] = "111"      # alex
    taylor = tools.get_free_slots(service_id="haircut", master_id="taylor", date_from=tomorrow)
    slot = taylor["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(service_id="haircut", master_id="taylor", start=slot["start"],
                                customer_name="Клиент Нины", phone="+598 99999999",
                                confirmation_token=slot["token"], ctx=confirmed_ctx)

    telegram_bot.handle_update(press("cancelled", made["booking_id"], "111"), tenant, store, "t")
    assert store.get_booking(made["booking_id"], tenant_id=tenant.slug).status == "confirmed"
    assert "другого мастера" in sent["answers"][0]


def test_unknown_command_shows_help(tenant, store, sent):
    tenant.salon["masters"][0]["telegramChatId"] = "111"
    telegram_bot.handle_update(message("привет", "111"), tenant, store, "t")
    assert "/today" in sent["messages"][-1][1]


def test_buttons_are_attached_to_a_booking(tools, tenant, store, tomorrow, confirmed_ctx):
    rows = telegram_bot.booking_buttons("abc123")
    flat = [b for row in rows for b in row]
    assert [b["callback_data"] for b in flat] == [
        "b:completed:abc123", "b:no_show:abc123",
        "p:cash:abc123", "p:card:abc123", "b:cancelled:abc123"]
    # Отмена — в отдельном ряду: её нажимают по инерции рядом с «пришёл».
    assert len(rows) == 3 and len(rows[-1]) == 1


def test_start_with_master_code_binds_the_chat(tenant, store, sent):
    """Мастер нажал «Начать» — и уже подключён, без похода в панель.

    При активном вебхуке апдейт достаётся ему, а не `getUpdates`: раньше
    «Связать чат» на это отвечала «ещё не открыл ссылку».
    """
    code = master_link_code(tenant.slug, "alex")
    telegram_bot.handle_update(message(f"/start {code}", "555"), tenant, store, "t")

    assert tenant.master("alex")["telegramChatId"] == "555"
    assert "Alex" in sent["messages"][-1][1]


def test_start_with_staff_code_binds_the_chat(tenant, store, sent):
    user = auth.create_user(store, "taylor@example.com", "Sup3r-Pass-9", name="Taylor")
    telegram_bot.handle_update(
        message(f"/start {user_link_code(user.id)}", "777"), tenant, store, "t")

    assert [u.telegram_chat_id for u in auth.list_users(store)] == ["777"]
    assert sent["messages"][-1][0] == "777"


def test_start_without_code_waits_for_the_panel(tenant, store, sent):
    """Владельцу бот не отвечает, но чат запоминает — его привяжет кнопка.

    Привязать сразу нельзя: тогда получателем уведомлений салона стал бы любой,
    кто первым написал боту.
    """
    telegram_bot.handle_update(message("/start", "42"), tenant, store, "t")

    assert sent["messages"] == []
    assert telegram_bot.pending_chat(store, tenant.slug)["id"] == "42"


def test_foreign_code_binds_nobody(tenant, store, sent):
    telegram_bot.handle_update(message("/start deadbeefdeadbeef", "666"), tenant, store, "t")

    assert not tenant.master("alex").get("telegramChatId")
    assert sent["messages"] == []


def test_stale_start_is_not_offered_to_the_panel(tenant, store, monkeypatch):
    """Вчерашнее «/start» не должно становиться адресом уведомлений салона."""
    telegram_bot.handle_update(message("/start", "42"), tenant, store, "t")
    monkeypatch.setattr(telegram_bot, "PENDING_TTL", timedelta(seconds=-1))

    assert telegram_bot.pending_chat(store, tenant.slug) is None


def test_start_from_a_linked_chat_shows_help(tenant, store, sent):
    tenant.salon["masters"][0]["telegramChatId"] = "111"
    telegram_bot.handle_update(message("/start", "111"), tenant, store, "t")

    assert "/today" in sent["messages"][-1][1]


def test_master_link_survives_the_whole_webhook_path(client, sent):
    """Тот же путь, что и в бою: апдейт от Telegram → роут → привязка → панель.

    Панельная кнопка после этого не ищет ничего в `getUpdates` (там уже пусто),
    а подтверждает привязанный чат.
    """
    from backend.app.tenants import registry

    registry.get("demo-salon").patch_integration({"handoff.telegramBotToken": "12345:token"})
    code = master_link_code("demo-salon", "alex")

    res = client.post("/api/telegram/demo-salon/webhook",
                      json=message(f"/start {code}", "555"),
                      headers={"X-Telegram-Bot-Api-Secret-Token": webhook_secret("demo-salon")})
    assert res.status_code == 200

    linked = client.post("/api/admin/telegram/masters/alex/link?tenant=demo-salon")
    assert linked.status_code == 200
    assert linked.json()["chatId"] == "555"


def test_webhook_secret_differs_between_tenants():
    assert webhook_secret("demo-salon") != webhook_secret("second-demo")
    assert webhook_secret("demo-salon") == webhook_secret("demo-salon")


def test_webhook_is_paused_while_reading_updates(monkeypatch):
    """getUpdates при активном вебхуке Telegram запрещает.

    Автоматическая установка вебхука сломала «Связать чат»: панель отвечала
    «Conflict: can't use getUpdates method while webhook is active».
    """
    calls = []
    monkeypatch.setattr(telegram, "webhook_info",
                        lambda token: {"url": "https://x/hook", "pending": 0, "error": ""})
    monkeypatch.setattr(telegram, "delete_webhook", lambda token: calls.append("delete"))
    monkeypatch.setattr(telegram, "set_webhook",
                        lambda token, url, secret, drop_pending=True:
                            calls.append(f"set:{url}:drop={drop_pending}"))

    with telegram.webhook_paused("t", secret="s"):
        calls.append("read")

    assert calls == ["delete", "read", "set:https://x/hook:drop=False"]


def test_no_webhook_means_nothing_to_pause(monkeypatch):
    """Пока вебхук не поставлен, привязка работает как раньше — без лишних вызовов."""
    calls = []
    monkeypatch.setattr(telegram, "webhook_info",
                        lambda token: {"url": "", "pending": 0, "error": ""})
    monkeypatch.setattr(telegram, "delete_webhook", lambda token: calls.append("delete"))
    monkeypatch.setattr(telegram, "set_webhook",
                        lambda *a, **k: calls.append("set"))

    with telegram.webhook_paused("t", secret="s"):
        calls.append("read")

    assert calls == ["read"]


def test_master_cancel_button_tells_the_client(tenant, store, tools, tomorrow, confirmed_ctx, monkeypatch):
    """Мастер жмёт «Отменить» — клиент узнаёт об этом, а не приходит зря."""
    from backend.app import telegram, telegram_bot

    tenant.salon["masters"][0]["telegramChatId"] = "555000"
    tenant.integration.setdefault("handoff", {})["telegramBotToken"] = "тестовый"
    monkeypatch.setattr(telegram, "send", lambda *a, **k: None)
    monkeypatch.setattr(telegram, "answer_callback", lambda *a, **k: None)
    monkeypatch.setattr(telegram, "edit_reply_markup", lambda *a, **k: None, raising=False)

    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(
        service_id="haircut", master_id="alex", start=slot["start"],
        customer_name="Jordan", phone="+598 91234567",
        confirmation_token=slot["token"], ctx=confirmed_ctx)

    telegram_bot.handle_update({"callback_query": {
        "id": "1", "data": f"b:cancelled:{made['booking_id']}",
        "message": {"chat": {"id": "555000"}, "message_id": 7},
    }}, tenant, store, "тестовый")

    tasks = [t for t in store.list_notifications(booking_id=made["booking_id"])
             if t.type == "booking_cancelled"]
    assert tasks and tasks[0].audience == "client" and tasks[0].status == "scheduled"
    # Напоминания при этом сняты: звать на отменённый визит нельзя.
    assert all(t.status == "cancelled" for t in store.list_notifications(booking_id=made["booking_id"])
               if t.type.startswith("booking_reminder"))
