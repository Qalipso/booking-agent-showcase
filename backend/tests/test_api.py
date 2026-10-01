"""HTTP-контракт: то, что видят виджет и админ-форма. Всё на временных файлах."""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from backend.tests.conftest import SALON


def test_health_lists_tenants(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert [t["slug"] for t in body["tenants"]] == ["demo-salon"]


def test_config_of_single_tenant_without_param(client):
    body = client.get("/api/config").json()
    assert body["tenant"] == "demo-salon"
    assert [s["id"] for s in body["services"]] == ["haircut", "color"]


def test_config_tells_the_widget_how_a_local_number_looks(client):
    """Виджет проверяет телефон правилом сервера, а не своей копией правила.

    Своя копия разошлась с сервером: виджет пропускал номер, на который запись
    отвечала отказом уже после сводки, — и поправить его было негде.
    """
    salon = client.get("/api/config").json()["salon"]
    assert salon["phoneCountry"] == "598"
    assert salon["phoneLengths"] == [8, 9]


def test_slots_carry_signed_token(client, tomorrow):
    body = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut", "date": tomorrow}).json()
    assert body["slots"]
    assert all(len(s["token"]) == 32 for s in body["slots"])


def test_master_service_mismatch_is_400(client, tomorrow):
    res = client.get("/api/slots", params={"masterId": "taylor", "serviceId": "color", "date": tomorrow})
    assert res.status_code == 400


def test_book_then_double_book_conflicts(client, tomorrow):
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut", "date": tomorrow}).json()["slots"]
    payload = {
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Jordan", "phone": "+598 91234567", "token": slots[0]["token"],
    }
    assert client.post("/api/book", json=payload).status_code == 200
    assert client.post("/api/book", json={**payload, "name": "Другой", "phone": "+598 99999999"}).status_code == 409


def test_chat_disabled_returns_409(client):
    assert client.post("/api/chat", json={"message": "привет"}).status_code == 409


def test_unknown_tenant_is_404(client):
    assert client.get("/api/config", params={"tenant": "нет-такого"}).status_code == 404


# --- мультиарендность --------------------------------------------------------

def test_create_and_list_tenants(client):
    res = client.post("/api/admin/tenants", json={"slug": "second-demo", "title": "Second Demo"})
    assert res.status_code == 200
    assert {t["slug"] for t in res.json()["tenants"]} == {"demo-salon", "second-demo"}


def test_slug_is_validated(client):
    assert client.post("/api/admin/tenants", json={"slug": "Плохой Код", "title": "X"}).status_code == 422


def test_duplicate_slug_rejected(client):
    client.post("/api/admin/tenants", json={"slug": "second-demo", "title": "Second Demo"})
    assert client.post("/api/admin/tenants", json={"slug": "second-demo", "title": "Ещё"}).status_code == 422


def test_copy_does_not_carry_secrets(client, tenants_dir):
    """Новый бизнес наследует услуги, но не чужие ключи и календари."""
    from backend.app.tenants import Tenant

    donor = Tenant("demo-salon")
    donor.integration["ai"] = {**donor.integration["ai"], "enabled": True, "apiKey": "secret-key"}
    donor.integration["mode"] = "oauth"
    donor.integration["refreshToken"] = "secret-refresh"
    donor.save_form({**donor.form_data(), "ai": {**donor.ai, "apiKey": "secret-key", "enabled": False}})

    client.post("/api/admin/tenants", json={"slug": "copy-lab", "title": "Copy", "copyFrom": "demo-salon"})
    clone = Tenant("copy-lab")
    assert [s["id"] for s in clone.services] == [s["id"] for s in donor.services]
    assert clone.integration["mode"] == "local"
    assert not clone.integration.get("refreshToken")
    assert not clone.ai.get("apiKey")


def test_tenants_are_isolated(client, tomorrow):
    """Запись в одном бизнесе не занимает то же время в другом."""
    client.post("/api/admin/tenants", json={"slug": "second-demo", "title": "Second Demo", "copyFrom": "demo-salon"})

    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow, "tenant": "demo-salon"}).json()["slots"]
    booked = client.post("/api/book", params={"tenant": "demo-salon"}, json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Jordan", "phone": "+598 91234567", "token": slots[0]["token"],
    })
    assert booked.status_code == 200, booked.text

    other = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow, "tenant": "second-demo"}).json()["slots"]
    assert slots[0]["time"] in [s["time"] for s in other], "чужая запись не должна занимать слот"


def test_token_of_one_tenant_rejected_in_another(client, tomorrow):
    client.post("/api/admin/tenants", json={"slug": "second-demo", "title": "Second Demo", "copyFrom": "demo-salon"})
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow, "tenant": "demo-salon"}).json()["slots"]
    res = client.post("/api/book", params={"tenant": "second-demo"}, json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Jordan", "phone": "+598 91234567", "token": slots[0]["token"],
    })
    assert res.status_code == 400
    assert "не предлагалось" in res.json()["detail"]


def test_config_is_per_tenant(client):
    client.post("/api/admin/tenants", json={"slug": "second-demo", "title": "Second Demo"})
    data = client.get("/api/admin/config", params={"tenant": "second-demo"}).json()["data"]
    data["salon"]["name"] = "Second Demo 2"
    data["salon"]["address"] = "Пунта-Карретас, Монтевидео"  # у нового бизнеса адрес обязателен
    assert client.put("/api/admin/config", params={"tenant": "second-demo"}, json=data).status_code == 200

    assert client.get("/api/config", params={"tenant": "second-demo"}).json()["salon"]["name"] == "Second Demo 2"
    assert client.get("/api/config", params={"tenant": "demo-salon"}).json()["salon"]["name"] == SALON["name"]


def test_last_tenant_cannot_be_deleted(client):
    assert client.delete("/api/admin/tenants/demo-salon").status_code == 422


def test_delete_tenant(client):
    client.post("/api/admin/tenants", json={"slug": "second-demo", "title": "Second Demo"})
    res = client.delete("/api/admin/tenants/second-demo")
    assert res.status_code == 200
    assert [t["slug"] for t in res.json()["tenants"]] == ["demo-salon"]


def test_embed_snippet_contains_tenant(client):
    body = client.get("/api/admin/embed", params={"tenant": "demo-salon", "origin": "https://bot.example.com"}).json()
    assert 'data-tenant="demo-salon"' in body["snippet"]
    assert body["demo"].endswith("?tenant=demo-salon")


def test_admin_config_masks_secrets(client):
    from backend.app.schema import MASK

    data = client.get("/api/admin/config").json()["data"]
    data["handoff"] = {**data["handoff"], "telegramBotToken": "secret-token"}
    client.put("/api/admin/config", json=data)
    fresh = client.get("/api/admin/config").json()["data"]
    assert fresh["handoff"]["telegramBotToken"] == MASK


def test_admin_rejects_invalid_config(client):
    data = client.get("/api/admin/config").json()["data"]
    data["salon"]["name"] = ""
    res = client.put("/api/admin/config", json=data)
    assert res.status_code == 422
    assert any("Название" in e for e in res.json()["detail"]["errors"])


def test_whatsapp_verify_requires_token(client):
    res = client.get("/webhook/whatsapp/demo-salon",
                     params={"hub.mode": "subscribe", "hub.verify_token": "wrong"})
    assert res.status_code == 403


def test_admin_creates_booking_through_the_same_path(client, tomorrow):
    """Ручная запись из панели проходит те же проверки, что и виджет."""
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    res = client.post("/api/admin/bookings", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow,
        "time": slots[0]["time"], "name": "Мария", "phone": "+598 99123456",
    })
    assert res.status_code == 200, res.text
    assert res.json()["booking"]["master"] == "Alex"

    # Тот же слот второй раз — конфликт, а не вторая запись поверх первой.
    again = client.post("/api/admin/bookings", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow,
        "time": slots[0]["time"], "name": "Другой", "phone": "+598 90000000",
    })
    assert again.status_code == 409


def test_admin_booking_list_carries_card_fields(client, tomorrow):
    """Карточке записи нужны канал, комментарий и ссылка на событие."""
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    client.post("/api/admin/bookings", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow,
        "time": slots[0]["time"], "name": "Мария", "phone": "+598 99123456",
        "comment": "просила колориста",
    })
    row = client.get("/api/admin/bookings").json()["bookings"][0]
    for key in ("masterId", "serviceId", "end", "comment", "createdAt", "channel", "notifyConsent"):
        assert key in row, key
    assert row["comment"] == "просила колориста"
    assert row["channel"] == "admin"


def test_notification_queue_is_readable(client, tomorrow):
    """Очередь уведомлений открывается по записи.

    Гвардия этого роутера жила отдельной обёрткой и после перехода на вход по
    сессии получала строку вместо Request — эндпоинт отдавал 500 на любой
    запрос, включая запрос с валидным токеном.
    """
    # Послезавтра, а не завтра: напоминание накануне ставится на 19:00, и после
    # семи вечера у записи «на завтра» этот момент уже позади — тест падал
    # каждый вечер, хотя очередь работала.
    from datetime import date, timedelta

    day = (date.fromisoformat(tomorrow) + timedelta(days=1)).isoformat()
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": day}).json()["slots"]
    booked = client.post("/api/admin/bookings", json={
        "masterId": "alex", "serviceId": "haircut", "date": day,
        "time": slots[0]["time"], "name": "Мария", "phone": "+598 99123456",
    })
    assert booked.status_code == 200, booked.text
    booking_id = booked.json()["booking"]["booking_id"]

    res = client.get("/api/notifications", params={"booking": booking_id})
    assert res.status_code == 200, res.text
    tasks = res.json()["notifications"]
    names = [t["notification_id"] for t in tasks]
    assert any("confirmed" in n for n in names), names
    assert any("reminder-day-before" in n for n in names), names
    assert {t["audience"] for t in tasks} >= {"client", "owner"}, tasks


def test_database_status_describes_live_storage(client, tomorrow):
    """Экран «База данных» показывает факты о базе, а не выбранное в форме.

    Раньше раздел спрашивал строку подключения, которую всё равно негде было
    сохранить: адрес базы приходит только из окружения. Теперь он отвечает на
    единственный вопрос владельца — жива ли база и сколько в ней данных.
    """
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    client.post("/api/admin/bookings", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow,
        "time": slots[0]["time"], "name": "Мария", "phone": "+598 99123456",
    })

    body = client.get("/api/admin/database/status").json()
    assert body["ok"] is True, body
    assert body["kind"] == "sqlite"
    assert body["counts"]["bookings"] == 1, body
    assert body["sizeBytes"] > 0
    # Пароля и строки подключения в ответе быть не должно ни в каком виде.
    assert "url" not in body and "password" not in str(body).lower()


def test_database_check_writes_without_leaving_traces(client):
    """Проверка связи — настоящая запись: том мог оказаться только для чтения."""
    body = client.post("/api/admin/database/check").json()
    assert body["ok"] is True, body
    assert body["error"] == ""

    from backend.app import deps
    from sqlalchemy import text
    with deps.runtime.store.session_factory() as s:
        left = s.execute(text("select name from sqlite_master where name like '%selftest%'")).all()
    assert left == [], left


def test_database_provider_is_recognised_by_host():
    """Подключённый Supabase должен выглядеть Supabase, а не «внешней базой»."""
    from backend.app.db import _provider

    assert _provider("db") == "service"
    assert _provider("aws-0-eu-central-1.pooler.supabase.com") == "Supabase"
    assert _provider("ep-cool-forest.eu-central-1.aws.neon.tech") == "Neon"
    assert _provider("db.hetzner.example.com") == "external"
    assert _provider("", sqlite=True) == "file"


def test_telegram_connect_keeps_token_out_of_the_json_file(client, tenants_dir, monkeypatch):
    """Токен бота уходит в хранилище секретов, а не в файл бизнеса.

    integration.json лежит в репозитории и уезжает в GitHub. Патч интеграции
    собирается плоскими путями именно поэтому: собрать его из `tenant.handoff`
    значило бы записать в файл уже подмешанный туда секрет.
    """
    from backend.app import telegram

    monkeypatch.setattr(telegram, "me", lambda token: {"id": 1, "username": "mosa_bot", "title": "Mosa"})

    res = client.post("/api/admin/telegram/connect", json={"token": "123:AA"})
    assert res.status_code == 200, res.text
    assert res.json()["bot"] == "mosa_bot"

    raw = (tenants_dir / "demo-salon" / "integration.json").read_text(encoding="utf-8")
    assert "123:AA" not in raw

    status = client.get("/api/admin/telegram/status").json()
    assert status["hasToken"] is True and status["connected"] is False, status


def test_telegram_link_finds_chat_and_switches_owner_channel(client, monkeypatch):
    """«Связать чат» заменяет ручной ввод chat_id и включает канал владельца."""
    from backend.app import telegram

    monkeypatch.setattr(telegram, "me", lambda token: {"id": 1, "username": "mosa_bot", "title": "Mosa"})
    client.post("/api/admin/telegram/connect", json={"token": "123:AA"})

    monkeypatch.setattr(telegram, "find_chat",
                        lambda token: {"id": "-100500", "title": "Салон", "type": "group"})
    res = client.post("/api/admin/telegram/link")
    assert res.status_code == 200, res.text
    assert res.json()["chatId"] == "-100500"

    data = client.get("/api/admin/config").json()["data"]
    assert data["handoff"]["telegramChatId"] == "-100500"
    # Провайдер владельца живёт на экране внутренних уведомлений; в файле
    # конфигурации это по-прежнему одна секция `notifications`.
    assert data["notificationsInternal"]["ownerProvider"] == "telegram"


def test_telegram_link_without_messages_explains_what_to_do(client, monkeypatch):
    from backend.app import telegram

    monkeypatch.setattr(telegram, "me", lambda token: {"id": 1, "username": "mosa_bot", "title": "Mosa"})
    client.post("/api/admin/telegram/connect", json={"token": "123:AA"})
    monkeypatch.setattr(telegram, "find_chat", lambda token: None)

    res = client.post("/api/admin/telegram/link")
    assert res.status_code == 422
    assert "/start" in res.json()["detail"]


def test_ai_connect_rejects_a_key_the_provider_refuses(client, monkeypatch):
    """Нерабочий ключ не должен попадать в настройки: бот молчал бы без причины."""
    from backend.app import ai_providers

    def refuse(provider, key):
        raise ai_providers.ProviderError("Google AI Studio не принял ключ — скопируйте его заново")

    monkeypatch.setattr(ai_providers, "verify", refuse)
    res = client.post("/api/admin/ai/connect", json={"provider": "google", "apiKey": "bad"})
    assert res.status_code == 422
    assert "не принял ключ" in res.json()["detail"]
    assert client.get("/api/admin/ai/status").json()["hasKey"] is False


def test_ai_connect_saves_provider_and_falls_back_to_an_available_model(client, tenants_dir, monkeypatch):
    """Имя модели у бесплатных провайдеров живёт своей жизнью — подбираем доступную."""
    from backend.app import ai_providers

    monkeypatch.setattr(ai_providers, "verify", lambda provider, key: ["gemini-2.5-flash-latest", "gemini-2.5-pro"])
    res = client.post("/api/admin/ai/connect",
                      json={"provider": "google", "apiKey": "k-secret", "model": "gemini-2.5-flash"})
    assert res.status_code == 200, res.text
    assert res.json()["model"] == "gemini-2.5-flash-latest"

    status = client.get("/api/admin/ai/status").json()
    assert status["enabled"] is True and status["provider"] == "google"
    assert {p["id"] for p in status["providers"]} == {"google", "groq", "openai", "anthropic"}

    raw = (tenants_dir / "demo-salon" / "integration.json").read_text(encoding="utf-8")
    assert "k-secret" not in raw


def test_free_providers_speak_chat_completions(client):
    """Google и Groq ходят по /chat/completions: Responses API есть только у OpenAI."""
    from backend.app.agent import _ChatClient, _OpenAIClient, _openai_client

    google = _openai_client({"provider": "google", "apiKey": "k", "model": "gemini-2.5-flash"})
    assert isinstance(google, _ChatClient)
    assert isinstance(_openai_client({"provider": "openai", "apiKey": "k", "model": "gpt-4.1-mini"}),
                      _OpenAIClient)


def test_unfinished_google_setup_does_not_lock_the_whole_form(client):
    """Незаконченное подключение Google не должно запирать сохранение панели.

    Правило «для OAuth нужен refresh token» создавало тупик: токен выдаётся
    только после входа в Google, а войти было нельзя — конфигурация с режимом
    oauth не сохранялась, и введённые Client ID с Secret не доживали до кнопки
    входа. Заодно блокировались правки в разделах, к Google отношения не
    имеющих.
    """
    data = client.get("/api/admin/config").json()["data"]
    data["integration"] |= {"mode": "oauth", "clientId": "abc.apps.googleusercontent.com",
                            "clientSecret": "s", "refreshToken": ""}
    data["salon"]["name"] = "Новое имя"

    res = client.put("/api/admin/config", json=data)
    assert res.status_code == 200, res.text
    assert res.json()["data"]["salon"]["name"] == "Новое имя"


def test_google_credentials_are_saved_outside_the_form(client, tenants_dir):
    """Client ID и Secret сохраняются кнопкой и мимо валидации всей конфигурации."""
    res = client.post("/api/admin/google/credentials",
                      json={"clientId": "abc.apps.googleusercontent.com", "clientSecret": "s3cret"})
    assert res.status_code == 200, res.text

    status = client.get("/api/admin/google/status").json()
    assert status["hasClientCredentials"] is True, status
    assert status["connected"] is False

    raw = (tenants_dir / "demo-salon" / "integration.json").read_text(encoding="utf-8")
    assert "s3cret" not in raw


def test_google_credentials_reject_half_filled_input(client):
    res = client.post("/api/admin/google/credentials", json={"clientId": "abc", "clientSecret": " "})
    assert res.status_code == 422


def test_missing_ai_key_does_not_lock_the_form_either(client):
    """«Включено, ключа нет» — не ошибка формы, а состояние карточки.

    Ключ живёт в окружении или в хранилище секретов, а `enabled` — в файле
    бизнеса. После переезда на другой сервер они расходятся, и правило «нужен
    API-ключ» запирало панель целиком: нельзя было даже поправить часы работы.
    Бот при этом жив — просто ведёт кнопочный сценарий.
    """
    data = client.get("/api/admin/config").json()["data"]
    data["ai"] |= {"enabled": True, "apiKey": "", "provider": "groq"}
    data["salon"]["name"] = "Салон без ключа"

    res = client.put("/api/admin/config", json=data)
    assert res.status_code == 200, res.text

    status = client.get("/api/admin/ai/status").json()
    assert status["degraded"] is True, status


def test_broken_date_and_time_are_rejected_not_crashed(client, tomorrow):
    """Кривые дата и время — ошибка запроса, а не 500.

    Раньше строка вроде «завтра» долетала до `date.fromisoformat`, ValueError
    поднимался до обработчика ASGI, и клиент получал «Internal Server Error»,
    а в логах оставался трейс, неотличимый от настоящей поломки сервиса.
    """
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    good = {"masterId": "alex", "serviceId": "haircut", "date": tomorrow,
            "time": slots[0]["time"], "name": "Мария", "phone": "+598 99123456"}

    assert client.post("/api/book", json=good | {"time": "00 мусор"}).status_code == 422
    assert client.post("/api/book", json=good | {"time": "25:00"}).status_code == 422
    assert client.post("/api/book", json=good | {"date": "завтра"}).status_code == 422
    assert client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                            "date": "завтра"}).status_code == 422
    assert client.post("/api/admin/bookings", json=good | {"date": "12-08-2026"}).status_code == 422

    # Исправный запрос по-прежнему проходит — проверка не задела рабочий путь.
    assert client.post("/api/book", json=good).status_code == 200


def test_bad_date_reaching_the_calculations_answers_422(client):
    """Страховка на случай пути без схемы: дата долетает до расчётов и оттуда.

    Например, из инструментов модели или из будущего эндпоинта, где `date`
    объявят без шаблона.
    """
    from backend.app.timeutil import BadDate, zoned

    with pytest.raises(BadDate):
        zoned("послезавтра", "11:00", "UTC")
    with pytest.raises(BadDate):
        zoned("2026-08-12", "полдень", "UTC")

    res = client.get("/api/admin/schedule", params={"date": "не дата"})
    assert res.status_code == 422, res.text


def test_validation_errors_are_a_readable_string(client, tomorrow):
    """Отказ схемы приходит строкой с именем поля, а не списком объектов.

    Виджет печатает `detail` клиенту как есть — стандартный формат pydantic
    превращался на экране в «[object Object]».
    """
    res = client.post("/api/book", json={"masterId": "alex", "serviceId": "haircut",
                                         "date": "завтра", "time": "11:00",
                                         "name": "Мария", "phone": "+598 99123456"})
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert isinstance(detail, str), detail
    assert "date" in detail and "формат" in detail, detail


# --- календарь смен -----------------------------------------------------------

def test_shift_calendar_closes_and_opens_days(client, tomorrow):
    """Мастер сам правит свой график на дату — виджет сразу это учитывает."""
    off = client.put("/api/admin/masters/alex/shifts",
                     json={"date": tomorrow, "mode": "off"})
    assert off.status_code == 200, off.text
    day = next(d for d in off.json()["days"] if d["date"] == tomorrow)
    assert day["works"] is False and day["source"] == "off"

    days = client.get("/api/days", params={"masterId": "alex"}).json()["days"]
    assert tomorrow not in [d["date"] for d in days]

    back = client.put("/api/admin/masters/alex/shifts",
                      json={"date": tomorrow, "mode": "work", "start": "12:00", "end": "14:00"})
    assert back.status_code == 200, back.text
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    assert [s["time"] for s in slots] == ["12:00", "12:30", "13:00"]


def test_shift_outside_salon_hours_is_refused(client, tomorrow):
    """Смена за пределами часов салона не дала бы ни одного окна."""
    res = client.put("/api/admin/masters/alex/shifts",
                     json={"date": tomorrow, "mode": "work", "start": "08:00", "end": "10:00"})
    assert res.status_code == 400
    assert "11:00" in res.json()["detail"]


def test_day_off_over_existing_bookings_asks_first(client, tomorrow):
    """Записи от выходного не исчезают — мастер должен подтвердить, что видит их."""
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    client.post("/api/admin/bookings", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow,
        "time": slots[0]["time"], "name": "Мария", "phone": "+598 99123456",
    })
    blocked = client.put("/api/admin/masters/alex/shifts", json={"date": tomorrow, "mode": "off"})
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["bookings"] == 1

    forced = client.put("/api/admin/masters/alex/shifts",
                        json={"date": tomorrow, "mode": "off", "force": True})
    assert forced.status_code == 200


def test_saving_settings_keeps_the_shift_calendar(client, tomorrow):
    """Форма смен не показывает — и не должна их стирать при сохранении."""
    client.put("/api/admin/masters/alex/shifts", json={"date": tomorrow, "mode": "off"})
    config = client.get("/api/admin/config").json()["data"]
    saved = client.put("/api/admin/config", json=config)
    assert saved.status_code == 200, saved.text

    # Месяц запрашиваем явно: в последний день месяца «завтра» уже в следующем.
    days = client.get("/api/admin/masters/alex/shifts",
                      params={"month": tomorrow[:7]}).json()["days"]
    assert next(d for d in days if d["date"] == tomorrow)["source"] == "off"


# --- расписание диапазоном ----------------------------------------------------

def test_schedule_range_returns_a_day_per_date(client, tomorrow):
    """Сетка расписания получает весь период одним ответом."""
    from datetime import date, timedelta

    start = date.fromisoformat(tomorrow)
    end = start + timedelta(days=6)
    res = client.get("/api/admin/schedule/range",
                     params={"from": start.isoformat(), "to": end.isoformat()})
    assert res.status_code == 200, res.text
    data = res.json()

    assert [d["date"] for d in data["days"]] == [(start + timedelta(days=i)).isoformat() for i in range(7)]
    assert {m["id"] for m in data["masters"]} == {"alex", "taylor"}
    # Колонки идут в том же порядке, что и мастера: сетка красит их по индексу.
    for day in data["days"]:
        assert [c["masterId"] for c in day["columns"]] == [m["id"] for m in data["masters"]]
        for col in day["columns"]:
            assert col["workHours"]["start"] and col["workHours"]["end"]


def test_schedule_range_shows_a_booking_on_its_own_day(client, tomorrow):
    """Запись попадает ровно в тот день, на который её сделали."""
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    booked = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow,
        "time": slots[0]["time"], "name": "Мария", "phone": "+598 99123456"})
    assert booked.status_code == 200, booked.text

    days = client.get("/api/admin/schedule/range",
                      params={"from": tomorrow, "to": tomorrow}).json()["days"]
    events = [e for col in days[0]["columns"] for e in col["events"]]
    assert [e["client"] for e in events] == ["Мария"]
    assert events[0]["start"] == slots[0]["time"]


def test_schedule_range_rejects_a_backwards_or_huge_period(client):
    """Период задом наперёд и период на год — ошибка запроса, а не молчаливый ответ."""
    assert client.get("/api/admin/schedule/range",
                      params={"from": "2026-08-10", "to": "2026-08-01"}).status_code == 422
    assert client.get("/api/admin/schedule/range",
                      params={"from": "2026-01-01", "to": "2026-12-31"}).status_code == 422
    assert client.get("/api/admin/schedule/range",
                      params={"from": "не дата", "to": "2026-08-01"}).status_code == 422


class FakeFreeBusy:
    """Google freebusy в памяти. Считает запросы: сетка расписания обязана
       спрашивать занятость один раз на мастера за весь период, а не по разу
       на каждый день."""

    def __init__(self, spans: list[tuple[str, str]]) -> None:
        self.spans = spans
        self.calls: list[tuple[str, str, str]] = []

    def freebusy(self):
        return self

    def query(self, *, body):
        self.calls.append((body["items"][0]["id"], body["timeMin"], body["timeMax"]))
        spans, items = self.spans, body["items"]

        class Call:
            def execute(self):
                return {"calendars": {items[0]["id"]:
                        {"busy": [{"start": a, "end": b} for a, b in spans]}}}
        return Call()


def test_schedule_range_asks_google_once_per_master(client, tomorrow):
    """Занятость за неделю — один запрос на мастера, а не семь."""
    from datetime import date, timedelta

    from backend.app import deps

    start = date.fromisoformat(tomorrow)
    end = start + timedelta(days=6)
    # Событие через полночь: часть попадает в один день, часть в следующий.
    day3 = (start + timedelta(days=2)).isoformat()
    day4 = (start + timedelta(days=3)).isoformat()
    fake = FakeFreeBusy([(f"{day3}T22:00:00-03:00", f"{day4}T02:00:00-03:00")])
    rt = deps.runtime.for_tenant("demo-salon")
    rt.calendar._client = fake        # noqa: SLF001 — подмена транспорта
    rt.calendar.mode = "google"

    days = client.get("/api/admin/schedule/range",
                      params={"from": start.isoformat(), "to": end.isoformat()}).json()["days"]

    # Два мастера — два запроса на весь период, а не по одному на каждый день.
    assert len(fake.calls) == 2, fake.calls
    assert {(c[1][:10], c[2][:10]) for c in fake.calls} == {
        (start.isoformat(), (end + timedelta(days=1)).isoformat())}

    def busy_on(date_str):
        day = next(d for d in days if d["date"] == date_str)
        return [(e["start"], e["end"]) for c in day["columns"] for e in c["events"]
                if e["kind"] == "external"]

    # Хвост события до утра обрезан по суткам с обеих сторон, а не потерян
    # и не свёрнут в полоску нулевой высоты наверху следующего дня.
    assert ("22:00", "24:00") in busy_on(day3)
    assert ("00:00", "02:00") in busy_on(day4)
    assert busy_on((start + timedelta(days=1)).isoformat()) == []


def test_schedule_range_survives_a_broken_calendar(client, tomorrow):
    """Отказ Google — пометка на колонке, а не пустое расписание."""
    from backend.app import deps
    from backend.tests.test_google import FakeClient

    rt = deps.runtime.for_tenant("demo-salon")
    rt.calendar._client = FakeClient({}, fail="Forbidden")   # noqa: SLF001 — без freebusy вовсе
    rt.calendar.mode = "google"

    res = client.get("/api/admin/schedule/range", params={"from": tomorrow, "to": tomorrow})
    assert res.status_code == 200, res.text
    columns = res.json()["days"][0]["columns"]
    assert columns and all(c["error"] == "Календарь недоступен" for c in columns)


def test_schedule_shows_time_in_the_salon_zone(client, tomorrow):
    """Время записи в расписании — по часам салона, а не по часам сервера.

    SQLite таймзону не хранит, и без нормализации на границе БД `astimezone()`
    принимал naive-время за локальное время машины: одна и та же запись
    показывалась как 11:00 на стенде в UTC и как 14:00 на стенде в UTC-3.
    """
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    client.post("/api/book", json={"masterId": "alex", "serviceId": "haircut", "date": tomorrow,
                                   "time": slots[0]["time"], "name": "Мария", "phone": "+598 99123456"})

    day = client.get("/api/admin/schedule", params={"date": tomorrow}).json()
    events = [e for c in day["columns"] for e in c["events"]]
    assert [e["start"] for e in events] == [slots[0]["time"]]


# --- отдельный календарь мастеру ---------------------------------------------

def test_master_calendar_needs_google_first(client):
    """Без подключённого Google создавать нечего — и это видно из ответа."""
    res = client.post("/api/admin/masters/alex/calendar", json={"title": ""})
    assert res.status_code == 400
    assert "Google" in res.json()["detail"]


def test_master_calendar_is_created_and_bound(client, tenants_dir, monkeypatch):
    """Кнопка заводит календарь и сразу привязывает его к карточке мастера."""
    import json

    from backend.app import google_oauth
    from backend.app.tenants import registry

    calls = []

    def fake_create(tenant, summary, description=""):
        calls.append((tenant.slug, summary))
        return {"id": "cal-alex@group.calendar.google.com", "title": summary}

    monkeypatch.setattr(google_oauth, "create_calendar", fake_create)
    monkeypatch.setattr(google_oauth, "list_calendars", lambda tenant: [])
    registry.get("demo-salon").patch_integration({"mode": "oauth"})

    res = client.post("/api/admin/masters/alex/calendar", json={"title": ""})
    assert res.status_code == 200, res.text
    assert res.json()["calendarId"] == "cal-alex@group.calendar.google.com"
    assert calls and "Demo Salon" in calls[0][1]

    salon = json.loads((tenants_dir / "demo-salon" / "salon.json").read_text(encoding="utf-8"))
    alex = next(m for m in salon["masters"] if m["id"] == "alex")
    assert alex["calendarId"] == "cal-alex@group.calendar.google.com"


def test_master_calendar_stays_after_the_form_is_saved(client, monkeypatch):
    """Созданный календарь доживает до следующего сохранения настроек.

    `calendarId` — обычное поле формы (владелец выбирает календарь из списка),
    поэтому защищать его от формы, как скрытый чат мастера, нельзя. Панель
    подставляет новый ID себе сразу после создания — здесь проверяется, что
    круг «создали → перечитали → сохранили» ничего не теряет.
    """
    from backend.app import google_oauth
    from backend.app.tenants import registry

    monkeypatch.setattr(google_oauth, "create_calendar",
                        lambda tenant, summary, description="": {"id": "cal-x@group.calendar.google.com",
                                                                 "title": summary})
    monkeypatch.setattr(google_oauth, "list_calendars", lambda tenant: [])
    registry.get("demo-salon").patch_integration({"mode": "oauth"})
    client.post("/api/admin/masters/alex/calendar", json={"title": ""})

    config = client.get("/api/admin/config").json()["data"]
    assert client.put("/api/admin/config", json=config).status_code == 200

    masters = client.get("/api/admin/config").json()["data"]["masters"]
    assert next(m for m in masters if m["id"] == "alex")["calendarId"] == "cal-x@group.calendar.google.com"


# --- страницы по ссылке из уведомления ----------------------------------------

def test_notification_links_open_a_real_page(client):
    """Оценка, лист ожидания и «мои записи» — обычные страницы, а не HTML в коде."""
    for path in ("/review/abc", "/waitlist/abc", "/manage/abc"):
        res = client.get(path, params={"token": "x", "tenant": "demo-salon"})
        assert res.status_code == 200, path
        assert "client.js" in res.text, path
        # Идентификатор и подпись страница читает из адреса — в разметке их нет.
        assert "abc" not in res.text, path


def test_button_link_glued_into_one_segment_still_opens(client):
    """Кнопка шаблона может привезти хвост адреса закодированным — разворачиваем.

    Meta подставляет в адрес кнопки только окончание, и приехать оно может
    одним куском: `/review/abc%3Ftenant%3Ddemo-salon`. Пока сервис отдавал на
    это обычную страницу, она искала подпись в `?query`, не находила и честно
    писала «ссылка недействительна».
    """
    res = client.get("/review/abc?tenant=demo-salon&token=x", follow_redirects=False)
    assert res.status_code == 200, "обычный адрес редиректить незачем"

    glued = client.get("/review/abc%3Ftenant%3Ddemo-salon%26token%3Dx", follow_redirects=False)
    assert glued.status_code == 302, glued.text
    assert glued.headers["location"] == "/review/abc?tenant=demo-salon&token=x"


def test_review_request_speaks_the_language_of_the_client(client, tomorrow):
    """Испанке из Монтевидео просьба оценить визит приходит по-испански и со ссылкой."""
    from backend.app import deps

    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    booked = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "María", "phone": "+598 99112233", "token": slots[0]["token"], "lang": "es",
    })
    assert booked.status_code == 200, booked.text
    booking_id = booked.json()["bookingId"]

    assert client.post(f"/api/admin/bookings/{booking_id}/status",
                       json={"status": "completed"}).status_code == 200

    tasks = deps.runtime.store.list_notifications(tenant_id="demo-salon")
    task = next((n for n in tasks if n.notification_id == f"booking-review-{booking_id}"), None)
    assert task is not None, "просьба об оценке не поставлена в очередь"
    assert "Puntúe su visita" in task.body, task.body
    assert "/review/" in task.body and "lang=es" in task.body, task.body
    assert task.lang == "es" and task.type == "review_request"


def test_waitlist_offer_can_actually_be_accepted(client, tomorrow):
    """Приём освободившегося места доводится до записи, а не до отказа подписи.

    Подпись слота считается по времени в поясе салона. Пока приём подписывал
    UTC-строку, клиент по ссылке из сообщения получал «это время не
    предлагалось» — предложение выглядело живым и не срабатывало ни разу.
    """
    from backend.app.policies import signed_action

    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    booked = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Jordan", "phone": "+598 91234567", "token": slots[0]["token"],
    })
    assert booked.status_code == 200, booked.text

    entry = client.post("/api/admin/waitlist", json={
        "name": "Мария", "phone": "+598 99112233", "serviceId": "haircut",
        "masterId": "alex", "dateFrom": tomorrow, "dateTo": tomorrow,
    }).json()["id"]
    assert client.post(f"/api/admin/bookings/{booked.json()['bookingId']}/status",
                       json={"status": "cancelled"}).status_code == 200

    token = signed_action("waitlist", "demo-salon", entry)
    taken = client.post(f"/api/waitlist/{entry}/accept", params={"token": token, "tenant": "demo-salon"})
    assert taken.status_code == 200, taken.text
    assert taken.json()["booking"]["time"] == slots[0]["time"]


def test_cancelled_slot_can_be_booked_again(client, tomorrow):
    """Отменённое время снова доступно — иначе каждая отмена убивала слот навсегда.

    Отменённая запись остаётся в таблице ради статистики. Пока уникальный индекс
    (бизнес, мастер, начало) действовал и на неё, сетка показывала это время
    свободным, клиент его выбирал, а «Подтвердить» отвечало «только что заняли».
    """
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    first = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Jordan", "phone": "+598 91234567", "token": slots[0]["token"],
    })
    assert first.status_code == 200, first.text
    assert client.post(f"/api/admin/bookings/{first.json()['bookingId']}/status",
                       json={"status": "cancelled"}).status_code == 200

    again = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Мария", "phone": "+598 99112233", "token": slots[0]["token"],
    })
    assert again.status_code == 200, again.text
    assert again.json()["bookingId"] != first.json()["bookingId"]


def test_panel_remembers_the_public_address(client, monkeypatch, tenants_dir):
    """Адрес для ссылок запоминается сам — по тому, как открыта панель.

    Иначе он живёт только в переменной окружения, и салон, где её забыли задать,
    молча рассылает сообщения без ссылок.
    """
    import json

    from backend.app.notify.service import public_base_url
    from backend.app.tenants import registry

    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    # Стенд разработчика запоминать нельзя: такую ссылку клиенту не отправишь.
    assert client.get("/api/admin/config").status_code == 200
    saved = json.loads((tenants_dir / "demo-salon" / "integration.json").read_text(encoding="utf-8"))
    assert not saved.get("publicBaseUrl")

    client.get("/api/admin/config", headers={"x-forwarded-proto": "https", "host": "demo-salon.com"})
    tenant = registry.get("demo-salon")
    assert tenant.integration.get("publicBaseUrl") == "https://demo-salon.com"
    assert public_base_url(tenant) == "https://demo-salon.com"

    # Переменная окружения сильнее запомненного адреса.
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://booking.example")
    assert public_base_url(tenant) == "https://booking.example"


def test_client_links_ignore_the_panel_domain(client, monkeypatch, tenants_dir):
    """Заданный домен клиентских ссылок сильнее запомненного адреса панели.

    Панель открывают по `admin.…`, и запомненный адрес уводил туда же ссылки для
    клиента — вместе с кнопкой утверждённого шаблона, где в Meta зашит другой
    домен: клиент нажимал и попадал на админский вход.
    """
    from backend.app.notify.service import public_base_url
    from backend.app.tenants import registry

    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    client.get("/api/admin/config", headers={"x-forwarded-proto": "https", "host": "admin.demo-salon.com"})
    tenant = registry.get("demo-salon")
    assert tenant.integration.get("publicBaseUrl") == "https://admin.demo-salon.com"

    tenant.patch_integration({"clientBaseUrl": "https://bookings.demo-salon.com"})
    assert public_base_url(tenant) == "https://bookings.demo-salon.com"

    # Панель открыли ещё раз — клиентский домен от этого не меняется.
    client.get("/api/admin/config", headers={"x-forwarded-proto": "https", "host": "admin.demo-salon.com"})
    assert public_base_url(registry.get("demo-salon")) == "https://bookings.demo-salon.com"


def test_public_booking_page_is_shareable(client):
    """Страница записи на своём домене: имя салона, превью ссылки и виджет.

    Заголовок и Open Graph собираются на сервере: превью в WhatsApp строит
    краулер, а он JavaScript не выполняет.
    """
    res = client.get("/book/demo-salon")
    assert res.status_code == 200
    assert "Demo Salon" in res.text
    assert 'property="og:title"' in res.text
    assert "/widget.js" in res.text and 'data-tenant="demo-salon"' in res.text
    # Услуги и мастера подтягиваются тем же публичным конфигом, что и виджет.
    assert "/book.js" in res.text

    assert client.get("/book/demo-salon", params={"lang": "es"}).text.count('lang="es"') >= 1
    assert client.get("/book/no-such-salon").status_code == 404


# --- клиент, заведённый вручную -----------------------------------------------

def test_client_can_be_added_by_hand(client, tomorrow):
    """Карточку заводят и до первой записи — а будущая запись ложится в неё же.

    Телефон нормализуется так же, как при записи: иначе тот же человек,
    записавшийся через виджет, получит вторую карточку, и история визитов,
    неявок и LTV разъедется надвое.
    """
    created = client.post("/api/admin/clients", json={
        "name": "Патрисия", "phone": "+598 91-234-999", "lang": "es",
        "notes": "Ходит по утрам", "consent": True,
    })
    assert created.status_code == 200, created.text
    card = created.json()["client"]
    assert card["phone"] == "59891234999" and card["notes"] == "Ходит по утрам"

    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    booked = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Патрисия", "phone": "+598 91 234 999", "token": slots[0]["token"],
    })
    assert booked.status_code == 200, booked.text

    same_phone = [c for c in client.get("/api/admin/clients").json()["clients"]
                  if c["phone"] == "59891234999"]
    assert len(same_phone) == 1, same_phone
    detail = client.get(f"/api/admin/clients/{card['id']}").json()
    assert len(detail["bookings"]) == 1
    assert detail["notes"] == "Ходит по утрам"


def test_client_with_the_same_phone_is_not_duplicated(client):
    """Второй раз тот же телефон — не дубль, а отказ с ссылкой на существующего."""
    first = client.post("/api/admin/clients", json={"name": "Лусия", "phone": "+598 99000111"})
    assert first.status_code == 200

    again = client.post("/api/admin/clients", json={"name": "Lucia", "phone": "099 000 111"})
    assert again.status_code == 409
    assert again.json()["detail"]["clientId"] == first.json()["client"]["id"]

    assert client.post("/api/admin/clients", json={"name": "Кто-то", "phone": "12345"}).status_code == 400


def test_local_and_international_number_are_one_client(client, tomorrow):
    """«092…» и «+598 92…» — один человек, а не две карточки.

    Клиент набирает номер по-разному дома и в переписке. Пока ключом были
    просто цифры введённого, история визитов, неявок и LTV делилась пополам —
    и именно на ней держится вся CRM.
    """
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    assert client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Мария", "phone": "099 000 101", "token": slots[0]["token"],
    }).status_code == 200

    dup = client.post("/api/admin/clients", json={"name": "María", "phone": "+598 99 000 101"})
    assert dup.status_code == 409, dup.text

    cards = client.get("/api/admin/clients").json()["clients"]
    assert [c["phone"] for c in cards].count("59899000101") == 1
    assert len(cards) == 1, cards


def test_two_cards_of_one_person_are_merged(client, tomorrow):
    """Карточки, заведённые до канонизации ключа, сливаются в одну.

    Именно так выглядит база салона, работавшего до неё: один и тот же человек
    записан и как «099000101», и как «59899000101». Раньше запись такого клиента
    падала в 500 — переименование упиралось в уникальный номер.
    """
    from backend.app.deps import runtime

    old = runtime.store.upsert_client(tenant_id="demo-salon", phone="099000101", name="Мария")
    new = runtime.store.upsert_client(tenant_id="demo-salon", phone="59899000101", name="")
    runtime.store.change_loyalty(tenant_id="demo-salon", client_id=old.id, points=40, reason="Бонус")
    runtime.store.change_loyalty(tenant_id="demo-salon", client_id=new.id, points=25, reason="Бонус")

    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    booked = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Мария", "phone": "099 000 101", "token": slots[0]["token"],
    })
    assert booked.status_code == 200, booked.text

    cards = client.get("/api/admin/clients").json()["clients"]
    assert len(cards) == 1, cards
    assert cards[0]["id"] == old.id  # осталась старшая: на неё ведут прежние ссылки
    assert cards[0]["phone"] == "59899000101"
    assert cards[0]["loyalty"] == 65
    # Запись легла в ту же карточку, а не повисла отдельно.
    assert len(client.get(f"/api/admin/clients/{old.id}").json()["bookings"]) == 1


def test_black_list_survives_duplicate_cards(client, tomorrow):
    """Блокировка на любой из двух карточек одного номера закрывает запись."""
    from backend.app.deps import runtime

    runtime.store.upsert_client(tenant_id="demo-salon", phone="099000101", name="Мария")
    dup = runtime.store.upsert_client(tenant_id="demo-salon", phone="59899000101", name="María")
    runtime.store.patch_client(dup.id, tenant_id="demo-salon", fields={"blocked": True})

    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    booked = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Мария", "phone": "099 000 101", "token": slots[0]["token"],
    })
    assert booked.status_code == 400, booked.text
    # Виджету нужен код, чтобы показать отказ на языке клиента; текст остаётся для логов.
    assert booked.json()["detail"]["code"] == "blocked"
    assert "отключена" in booked.json()["detail"]["error"]


def test_blocked_client_cannot_book_in_any_phone_format(client, tomorrow):
    """Чёрный список не обходится сменой формата номера."""
    created = client.post("/api/admin/clients", json={"name": "María", "phone": "+598 99 000 101"})
    client.patch(f"/api/admin/clients/{created.json()['client']['id']}", json={"blocked": True})

    for phone in ("099 000 101", "+598 99 000 101", "59899000101"):
        slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                                 "date": tomorrow}).json()["slots"]
        answer = client.post("/api/book", json={
            "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
            "name": "María", "phone": phone, "token": slots[0]["token"],
        })
        assert answer.status_code == 400, f"{phone}: {answer.text}"


def test_no_show_history_survives_a_change_of_phone_format(client, tomorrow, store):
    """Неявки считаются по человеку, а не по написанию номера."""
    from backend.app.deps import runtime

    client.post("/api/admin/clients", json={"name": "Хуан", "phone": "+598 92 122 030"})
    card = runtime.store.client_by_phone("59892122030", tenant_id="demo-salon")
    for week in (1, 2, 3):
        start = datetime.now(timezone.utc) - timedelta(days=7 * week)
        runtime.store.create_booking(
            tenant_id="demo-salon", conversation_id=None, master_id="alex", service_id="haircut",
            start_at=start, end_at=start + timedelta(minutes=60),
            client_id=card.id, client_name="Хуан", phone="59892122030", lang="ru", source="direct")
    for booking in runtime.store.client_bookings(card.id, tenant_id="demo-salon"):
        runtime.store.set_booking_status(booking.id, "no_show", tenant_id="demo-salon")

    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    answer = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Хуан", "phone": "092 122 030", "token": slots[0]["token"],
    })
    assert answer.status_code == 200, answer.text
    fresh = runtime.store.get_booking(answer.json()["bookingId"], tenant_id="demo-salon")
    assert fresh.requires_confirmation is True


def test_duplicate_code_answers_409_not_500(client):
    """Опечатка в коде справочника — это 409 с человеческим текстом."""
    assert client.post("/api/admin/locations",
                       json={"code": "centro", "name": "Кордон"}).status_code == 200
    again = client.post("/api/admin/locations", json={"code": "centro", "name": "Кордон 2"})
    assert again.status_code == 409, again.text

    assert client.post("/api/admin/resources",
                       json={"code": "chair-1", "name": "Кресло"}).status_code == 200
    assert client.post("/api/admin/resources",
                       json={"code": "chair-1", "name": "Кресло 2"}).status_code == 409

    asset = {"kind": "certificate", "code": "GIFT-1", "title": "Сертификат"}
    assert client.post("/api/admin/assets", json=asset).status_code == 200
    assert client.post("/api/admin/assets", json=asset).status_code == 409


# --- справочники платформы: правка и удаление ---------------------------------

def test_location_can_be_renamed_and_removed(client):
    """Филиал правится и удаляется — но не пока к нему привязаны мастера.

    Мастер, чей филиал исчез, пропадает из записи молча: клиент видит «нет
    свободных мастеров» и уходит.
    """
    created = client.post("/api/admin/locations", json={
        "code": "centro", "name": "Центр", "address": "18 de Julio 1000"})
    assert created.status_code == 200, created.text
    location_id = created.json()["id"]

    renamed = client.patch(f"/api/admin/locations/{location_id}",
                           json={"name": "Centro", "address": "Av. 18 de Julio 1000"})
    assert renamed.status_code == 200, renamed.text
    assert next(x for x in client.get("/api/admin/locations").json()["locations"]
                if x["id"] == location_id)["name"] == "Centro"

    config = client.get("/api/admin/config").json()["data"]
    config["masters"][0]["locationId"] = location_id
    assert client.put("/api/admin/config", json=config).status_code == 200

    blocked = client.delete(f"/api/admin/locations/{location_id}")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["masters"] == [config["masters"][0]["name"]]

    config["masters"][0]["locationId"] = ""
    assert client.put("/api/admin/config", json=config).status_code == 200
    assert client.delete(f"/api/admin/locations/{location_id}").status_code == 200
    assert client.get("/api/admin/locations").json()["locations"] == []


def test_resource_keeps_its_future_bookings(client, tomorrow):
    """Занятое кресло не удаляется: связь каскадная, и запись осталась бы без него."""
    from backend.app import deps

    resource_id = client.post("/api/admin/resources", json={
        "code": "chair-1", "name": "Кресло 1", "kind": "chair", "capacity": 1}).json()["id"]
    assert client.patch(f"/api/admin/resources/{resource_id}",
                        json={"name": "Кресло у окна", "capacity": 2}).status_code == 200

    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    booking_id = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Jordan", "phone": "+598 91234567", "token": slots[0]["token"],
    }).json()["bookingId"]
    deps.runtime.store.assign_resource(booking_id, resource_id)

    busy = client.delete(f"/api/admin/resources/{resource_id}")
    assert busy.status_code == 409
    assert busy.json()["detail"]["bookings"] == 1

    assert client.post(f"/api/admin/bookings/{booking_id}/status",
                       json={"status": "cancelled"}).status_code == 200
    assert client.delete(f"/api/admin/resources/{resource_id}").status_code == 200


def test_asset_is_edited_and_removed_with_its_balance(client):
    """Абонемент правится, а при удалении ответ называет списанный остаток."""
    card = client.post("/api/admin/clients", json={"name": "Лусия", "phone": "+598 99000111"})
    asset = client.post("/api/admin/assets", json={
        "clientId": card.json()["client"]["id"], "kind": "membership",
        "code": "M-10", "title": "Десять визитов", "remainingUses": 10})
    assert asset.status_code == 200, asset.text
    asset_id = asset.json()["id"]

    assert client.patch(f"/api/admin/assets/{asset_id}",
                        json={"title": "Абонемент на 10", "remainingUses": 7}).status_code == 200
    row = client.get("/api/admin/assets").json()["assets"][0]
    assert row["title"] == "Абонемент на 10" and row["uses"] == 7

    removed = client.delete(f"/api/admin/assets/{asset_id}")
    assert removed.status_code == 200 and removed.json()["uses"] == 7
    assert client.get("/api/admin/assets").json()["assets"] == []


# --- переезд клиентской базы --------------------------------------------------

DIRTY_CSV = """﻿Имя;Телефон;Язык;Заметки;Теги;Согласие
María;+598 94 123 456;es;Ходит по утрам;VIP, цвет;да
Хуан;099 000 101;ru;;;нет
Пустой;;ru;без телефона;;да
Мусор;12345;ru;короткий номер;;да
Дубль;+59894123456;es;тот же номер второй раз;;да
"""


def test_client_import_previews_before_it_writes(client):
    """Предпросмотр показывает, что приедет, и ничего не меняет.

    Чужая выгрузка всегда грязная: точка с запятой вместо запятой, BOM, строки
    без телефона и дубли внутри самого файла.
    """
    preview = client.post("/api/admin/clients/import", json={"csv": DIRTY_CSV})
    assert preview.status_code == 200, preview.text
    report = preview.json()
    assert (report["created"], report["updated"], report["rejected"]) == (2, 0, 3)
    assert report["committed"] is False
    assert client.get("/api/admin/clients").json()["clients"] == []

    причины = {r["reason"] for r in report["rows"] if r["action"] == "rejected"}
    assert причины == {"нет телефона", "телефон не похож на настоящий",
                       "этот номер уже есть в файле"}


def test_client_import_writes_and_updates_without_duplicates(client):
    """Загрузка заводит новых, обновляет своих и не плодит карточки.

    Тот же человек в файле записан международным номером, а в базе — местным:
    ключ один, карточка должна остаться одна.
    """
    client.post("/api/admin/clients", json={"name": "Хуан старый", "phone": "099 000 101",
                                            "notes": "Заметка администратора"})

    done = client.post("/api/admin/clients/import", json={"csv": DIRTY_CSV, "commit": True})
    assert done.status_code == 200, done.text
    assert (done.json()["created"], done.json()["updated"]) == (1, 1)

    cards = client.get("/api/admin/clients").json()["clients"]
    assert len(cards) == 2, cards
    juan = next(c for c in cards if c["phone"] == "59899000101")
    # Пустая ячейка в файле — «не знаю», а не «сотри»: заметка администратора цела.
    assert juan["notes"] == "Заметка администратора"
    assert juan["consent"] is False

    maria = next(c for c in cards if c["phone"] == "59894123456")
    assert maria["name"] == "María" and maria["lang"] == "es"
    assert maria["tags"] == ["VIP", "цвет"]


def test_client_export_can_be_imported_back(client):
    """Выгрузка читается своим же импортом — переезд работает в обе стороны."""
    client.post("/api/admin/clients", json={"name": "Лусия", "phone": "+598 99000111",
                                            "notes": "любит утро"})
    dump = client.get("/api/admin/clients/export")
    assert dump.status_code == 200
    assert dump.headers["content-disposition"].endswith('clients-demo-salon.csv"')
    assert "Лусия" in dump.text and "59899000111" in dump.text

    back = client.post("/api/admin/clients/import", json={"csv": dump.text, "commit": True})
    assert back.status_code == 200, back.text
    assert (back.json()["created"], back.json()["updated"]) == (0, 1)
    assert len(client.get("/api/admin/clients").json()["clients"]) == 1


def test_client_import_without_a_phone_column_is_refused(client):
    """Файл без телефона грузить некуда — говорим это прямо, а не «0 строк»."""
    res = client.post("/api/admin/clients/import", json={"csv": "Имя;Заметки\nМария;тест\n"})
    assert res.status_code == 400
    assert "телефон" in res.json()["detail"]


def test_client_import_report_is_capped_for_huge_files(client):
    """Отчёт по большому файлу обрезан, а счётчики — по всему файлу.

    База салона на десятки тысяч человек иначе приехала бы в браузер целиком
    ради таблицы, которую всё равно никто не пролистает.
    """
    lines = ["Имя;Телефон"] + [f"Клиент {n};+5989{n:07d}" for n in range(1, 601)]
    report = client.post("/api/admin/clients/import",
                         json={"csv": "\n".join(lines)}).json()
    assert report["total"] == 600 and report["created"] == 600
    assert len(report["rows"]) == 500 and report["truncated"] == 100


# --- технические перерывы -----------------------------------------------------

def test_break_takes_the_time_out_of_the_grid(client, tomorrow):
    """Перерыв занимает время так же, как запись: окна на него не предлагаются.

    Закрыть обед можно было только целым выходным — из-за этого его либо
    занимали клиентом, либо мастер терял день ради часа.
    """
    before = [s["time"] for s in client.get("/api/slots", params={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow}).json()["slots"]]
    assert "13:00" in before, before

    made = client.post("/api/admin/time-blocks", json={
        "masterId": "alex", "date": tomorrow, "start": "13:00", "end": "14:00", "title": "Обед"})
    assert made.status_code == 200, made.text
    assert made.json()["block"]["title"] == "Обед"

    after = [s["time"] for s in client.get("/api/slots", params={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow}).json()["slots"]]
    # Час обеда и всё, что на него налезает: стрижка длится час.
    assert not [t for t in after if "12:30" <= t <= "13:30"], after

    blocks = client.get("/api/admin/time-blocks", params={"from": tomorrow}).json()["blocks"]
    assert [(b["start"], b["end"]) for b in blocks] == [("13:00", "14:00")]


def test_break_does_not_land_on_a_booking(client, tomorrow):
    """Поверх записи перерыв не ставится — клиент уже придёт."""
    slots = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                             "date": tomorrow}).json()["slots"]
    booked = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slots[0]["time"],
        "name": "Jordan", "phone": "+598 91234567", "token": slots[0]["token"]})
    assert booked.status_code == 200, booked.text

    clash = client.post("/api/admin/time-blocks", json={
        "masterId": "alex", "date": tomorrow, "start": slots[0]["time"], "end": "23:00"})
    assert clash.status_code == 409
    assert clash.json()["detail"]["bookings"] == 1


def test_break_is_removed_together_with_its_slot(client, tomorrow):
    """Снятый перерыв возвращает время в сетку окон."""
    block_id = client.post("/api/admin/time-blocks", json={
        "masterId": "alex", "date": tomorrow, "start": "15:00", "end": "16:00"}).json()["block"]["id"]
    assert not [s for s in client.get("/api/slots", params={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow}).json()["slots"]
        if s["time"] == "15:00"]

    assert client.delete(f"/api/admin/time-blocks/{block_id}").status_code == 200
    assert [s for s in client.get("/api/slots", params={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow}).json()["slots"]
        if s["time"] == "15:00"]
    assert client.get("/api/admin/time-blocks", params={"from": tomorrow}).json()["blocks"] == []
    assert client.delete(f"/api/admin/time-blocks/{block_id}").status_code == 404


def test_break_reaches_the_master_calendar(client_google, tomorrow):
    """Перерыв попадает в календарь мастера, иначе снаружи время свободно."""
    client, events = client_google
    made = client.post("/api/admin/time-blocks", json={
        "masterId": "alex", "date": tomorrow, "start": "13:00", "end": "14:00", "title": "Уборка"})
    assert made.status_code == 200, made.text
    assert made.json()["block"]["inCalendar"] is True
    assert any("Уборка" in str(e.get("summary")) for e in events.values()), events

    block_id = made.json()["block"]["id"]
    assert client.delete(f"/api/admin/time-blocks/{block_id}").status_code == 200
    # Событие снято вместе с перерывом: иначе в календаре висит призрак обеда.
    assert not [e for e in events.values() if "Уборка" in str(e.get("summary"))]



def test_slots_hide_bookings_missing_from_google(client, tomorrow):
    """Запись из базы закрывает окно даже тогда, когда Google о ней не знает.

    Событие могло не создаться, попасть в чужой календарь или не отдаться
    freebusy без прав. Раньше сетка окон верила одному Google, а проверка перед
    вставкой — базе: клиент выбирал показанное время и получал «это время
    пересекается с другой записью мастера» уже после ввода телефона.
    """
    from backend.app import deps

    booked = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": "15:00",
        "name": "Мария", "phone": "099000101",
    })
    assert booked.status_code == 200, booked.text

    rt = deps.runtime.for_tenant("demo-salon")
    rt.calendar._client = FakeFreeBusy([])   # noqa: SLF001 — Google «не видит» события
    rt.calendar.mode = "google"

    times = [s["time"] for s in client.get("/api/slots", params={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow}).json()["slots"]]

    assert "15:00" not in times, "занятое базой окно предлагать нельзя"
    assert times, "остальные окна остаются свободными"

    # И то же время повторной записью не проходит — источники сошлись.
    again = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": "15:00",
        "name": "Ана", "phone": "092122030",
    })
    assert again.status_code == 409

def test_button_flow_saves_the_conversation(client, tomorrow):
    """Кнопочная запись оставляет в панели переписку, а не пустую карточку."""
    lines = [
        {"role": "assistant", "text": "¡Hola! ¿Qué le interesa?"},
        {"role": "user", "text": "Corte de dama"},
        {"role": "assistant", "text": "¿Con quién le reservo?"},
        {"role": "user", "text": "Alex"},
    ]
    res = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": "16:00",
        "name": "Ана", "phone": "099000101", "lang": "es", "transcript": lines,
    })
    assert res.status_code == 200, res.text
    conv_id = res.json()["conversationId"]

    dialog = client.get(f"/api/admin/conversations/{conv_id}").json()
    saved = [(m["role"], m["content"]) for m in dialog["messages"]]
    assert saved[:4] == [(x["role"], x["text"]) for x in lines]


def test_transcript_is_not_duplicated_on_retry(client, tomorrow):
    """Вторая попытка после отказа продолжает тот же диалог, а не удваивает его."""
    lines = [{"role": "assistant", "text": "¿Qué día le viene bien?"},
             {"role": "user", "text": "mañana"}]
    first = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": "17:00",
        "name": "Ана", "phone": "099000101", "transcript": lines,
    })
    conv_id = first.json()["conversationId"]

    # Клиент выбрал другое время: виджет присылает ту же переписку с хвостом.
    second = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": "18:30",
        "name": "Ана", "phone": "099000101", "conversationId": conv_id,
        "transcript": [*lines, {"role": "user", "text": "18:30"}],
    })
    assert second.status_code == 200, second.text
    assert second.json()["conversationId"] == conv_id

    messages = client.get(f"/api/admin/conversations/{conv_id}").json()["messages"]
    assert [m["content"] for m in messages] == [
        "¿Qué día le viene bien?", "mañana", "18:30"]


def test_slot_check_accepts_free_time_off_the_menu_grid(client, tomorrow):
    """Меню раз в два часа, клиент пишет «в 16» — время свободно, запись проходит."""
    from backend.app.deps import runtime

    runtime.for_tenant("demo-salon").tenant.salon["slotStepMinutes"] = 120
    grid = [s["time"] for s in client.get("/api/slots", params={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow}).json()["slots"]]
    assert "16:00" not in grid
    base = {"masterId": "alex", "serviceId": "haircut", "date": tomorrow}
    assert client.post("/api/book", json={**base, "time": "15:00", "name": "Jordan",
                                          "phone": "+598 91234567"}).status_code == 200

    check = client.get("/api/slot-check", params={**base, "time": "16:00"}).json()
    assert check["free"] is True and check["slot"]["time"] == "16:00"
    res = client.post("/api/book", json={**base, "time": "16:00", "name": "Другой",
                                         "phone": "+598 99887766"})
    assert res.status_code == 200, res.text

    taken = client.get("/api/slot-check", params={**base, "time": "15:30"}).json()
    assert taken["free"] is False and taken["slot"] is None
    # 15:00 и 16:00 заняты: ближайшее — закончить к 15:00 или прийти к 17:00,
    # и варианты не повторяют друг друга с разницей в четверть часа.
    assert [s["time"] for s in taken["nearest"]] == ["13:30", "14:00", "17:00"]
