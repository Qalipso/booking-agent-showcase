"""Уведомления: планирование, перепроверка перед отправкой, повторы, статусы.

Ничего наружу не уходит — провайдер `console` пишет в лог, а сбои имитируются
подменой `providers.send`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db import _aware
from backend.app.notify import providers, service as notify_service
from backend.app.notify import templates
from backend.app.policies import slot_token
from backend.app.timeutil import MONTHS, now, tz as zone, zoned


@pytest.fixture
def booking(tools, tenant, store, tomorrow, confirmed_ctx):
    """Живая запись через полный путь инструмента — как её создаёт бот."""
    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    result = tools.create_booking(
        service_id="haircut", master_id="alex", start=slot["start"],
        customer_name="Jordan", phone="+598 91234567",
        confirmation_token=slot["token"], ctx=confirmed_ctx,
    )
    return store.get_booking(result["booking_id"], tenant_id=tenant.slug)


def _tasks(store, booking_id):
    return {t.notification_id: t for t in store.list_notifications(booking_id=booking_id)}


def test_booking_schedules_owner_confirmation_and_reminders(store, booking):
    tasks = _tasks(store, booking.id)
    assert f"booking-owner-{booking.id}" in tasks
    assert f"booking-confirmed-{booking.id}" in tasks
    # Запись на завтра: напоминание накануне и в день визита ещё впереди.
    assert f"booking-reminder-same-day-{booking.id}" in tasks


def test_scheduling_twice_creates_no_duplicates(store, notifications, tenant, booking):
    before = len(store.list_notifications(booking_id=booking.id))
    notifications.schedule_for_booking(booking, tenant)
    assert len(store.list_notifications(booking_id=booking.id)) == before


def test_no_consent_means_only_owner_is_notified(tools, store, tenant, tomorrow, confirmed_ctx):
    slots = tools.get_free_slots(service_id="haircut", master_id="taylor", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    result = tools.create_booking(
        service_id="haircut", master_id="taylor", start=slot["start"],
        customer_name="Без согласия", phone="+598 90000001",
        confirmation_token=slot["token"], notify_consent=False, ctx=confirmed_ctx,
    )
    audiences = {t.audience for t in store.list_notifications(booking_id=result["booking_id"])}
    assert audiences == {"owner"}


def test_cancelled_booking_cancels_pending_reminders(tools, store, booking, confirmed_ctx):
    tools.cancel_booking(booking_id=booking.id, ctx=confirmed_ctx)
    statuses = {t.status for t in store.list_notifications(booking_id=booking.id)}
    assert statuses <= {"cancelled", "sent", "delivered"}
    assert "scheduled" not in statuses


def test_guard_blocks_reminder_after_cancellation(store, notifications, booking):
    task = _tasks(store, booking.id)[f"booking-reminder-same-day-{booking.id}"]
    store.cancel_booking(booking.id)
    _, reason = notifications.guard(task)
    assert reason == "статус записи: cancelled"


def test_guard_blocks_reminder_when_time_changed(store, notifications, booking):
    task = _tasks(store, booking.id)[f"booking-reminder-same-day-{booking.id}"]
    store.patch_notification(task.notification_id,
                             {"booking_start_at": booking.start_at + timedelta(hours=2)})
    task = _tasks(store, booking.id)[task.notification_id]
    _, reason = notifications.guard(task)
    assert reason == "время записи изменилось"


def test_tick_sends_due_tasks_only(store, notifications, booking):
    sent = notifications.tick()
    assert sent >= 2  # владельцу и подтверждение клиенту — оба «на сейчас»
    tasks = _tasks(store, booking.id)
    assert tasks[f"booking-confirmed-{booking.id}"].status == "sent"
    assert tasks[f"booking-reminder-same-day-{booking.id}"].status == "scheduled"


def test_email_provider_sends_a_real_email_message(monkeypatch):
    sent = []

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.example.com", 587, providers.TIMEOUT)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def starttls(self, context):
            assert context is not None

        def login(self, username, password):
            assert (username, password) == ("booking", "secret")

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr(providers.smtplib, "SMTP", FakeSmtp)
    result = providers.send(
        provider="email", channel="email", to="owner@example.com",
        body="Новая запись", template_name="owner_new_booking",
        cfg={"host": "smtp.example.com", "port": 587, "security": "starttls",
             "username": "booking", "password": "secret", "from": "bot@example.com"},
    )

    assert result.status == "sent"
    assert sent[0]["To"] == "owner@example.com"
    assert "Новая запись" in sent[0].get_content()


def test_owner_email_is_queued_when_selected(store, notifications, tenant, booking):
    tenant.integration.setdefault("handoff", {})["adminEmail"] = "owner@example.com"
    tenant.integration.setdefault("notifications", {})["ownerProvider"] = "email"
    email_booking = store.create_booking(
        tenant_id=tenant.slug, master_id="alex", service_id="haircut",
        start_at=booking.start_at + timedelta(days=7), end_at=booking.end_at + timedelta(days=7),
        client_name="Email", phone="+59890000002", idempotency_key="owner-email",
    )

    created = notifications.schedule_for_booking(email_booking, tenant)

    owner = next(t for t in created if t.notification_id == f"booking-owner-{email_booking.id}")
    assert (owner.provider, owner.channel, owner.recipient) == ("email", "email", "owner@example.com")


def test_claim_is_idempotent_between_workers(store, notifications, booking):
    notifications.tick()
    assert notifications.tick() == 0  # второй воркер уже ничего не находит


def test_temporary_failure_is_retried_with_backoff(store, notifications, booking, monkeypatch):
    monkeypatch.setattr(providers, "send", _raise(providers.SendError("сеть", permanent=False)))
    monkeypatch.setattr(notify_service.providers, "send", _raise(providers.SendError("сеть", permanent=False)))

    notifications.tick()
    task = _tasks(store, booking.id)[f"booking-confirmed-{booking.id}"]
    assert task.status == "scheduled"
    assert task.attempts == 1
    assert _aware(task.scheduled_at) > datetime.now(timezone.utc)


def test_permanent_failure_falls_back_to_sms(store, notifications, booking, monkeypatch):
    monkeypatch.setattr(notify_service.providers, "send",
                        _raise(providers.SendError("неверный номер", permanent=True)))
    notifications.tick()
    tasks = _tasks(store, booking.id)
    failed = tasks[f"booking-confirmed-{booking.id}"]
    assert failed.status == "failed"
    fallback = tasks[f"booking-confirmed-{booking.id}-sms"]
    assert fallback.channel == "sms" and fallback.fallback_of == failed.notification_id


def test_delivery_status_webhook_marks_delivered(store, notifications, booking):
    notifications.tick()
    task = _tasks(store, booking.id)[f"booking-confirmed-{booking.id}"]
    updated = notifications.apply_provider_status(
        provider_message_id=task.provider_message_id, raw_status="delivered")
    assert updated.status == "delivered" and updated.delivered_at


def test_repeated_webhook_changes_nothing(store, notifications, booking):
    notifications.tick()
    task = _tasks(store, booking.id)[f"booking-confirmed-{booking.id}"]
    notifications.apply_provider_status(provider_message_id=task.provider_message_id,
                                        raw_status="delivered")
    again = notifications.apply_provider_status(provider_message_id=task.provider_message_id,
                                                raw_status="failed")
    assert again.status == "delivered"


def test_stuck_task_returns_to_queue(store, notifications, booking):
    task = _tasks(store, booking.id)[f"booking-confirmed-{booking.id}"]
    store.patch_notification(task.notification_id, {"status": "sending"})
    store.patch_notification(task.notification_id,
                             {"updated_at": datetime.now(timezone.utc) - timedelta(minutes=30)})
    assert store.recover_stuck_notifications(5) >= 1
    assert _tasks(store, booking.id)[task.notification_id].status == "scheduled"


def test_same_day_reminder_never_wakes_client_too_early(tenant, booking, store):
    """Запись в 11:00 при напоминании «за 3 часа» не должна уходить в 8 утра."""
    s = notify_service.settings_for(tenant)
    times = notify_service.reminder_times(booking, tenant, s)
    start = _aware(booking.start_at)
    if times["same_day"]:
        not_before = zoned(templates.local_date_key(start, tenant.timezone),
                           s.same_day_not_before, tenant.timezone)
        assert times["same_day"] >= not_before
        assert times["same_day"] < start


def test_reminder_in_the_past_is_not_scheduled(tenant, store, notifications):
    """Запись «через час» не получает вчерашнего напоминания."""
    soon = datetime.now(timezone.utc) + timedelta(hours=1)
    booking = store.create_booking(
        tenant_id=tenant.slug, master_id="alex", service_id="haircut",
        start_at=soon, end_at=soon + timedelta(hours=1),
        client_name="Скоро", phone="598900000", idempotency_key="k-soon",
    )
    notifications.schedule_for_booking(booking, tenant)
    names = set(_tasks(store, booking.id))
    assert f"booking-reminder-day-before-{booking.id}" not in names


def _staff(store, email, chat, *, role="admin", notify=True, active=True):
    from backend.app import auth as auth_mod
    user = auth_mod.create_user(store, email, "internal pass 55", role=role)
    auth_mod.update_user(store, user.id, telegram_chat_id=chat,
                         notify_new_booking=notify, is_active=active)
    return user


def test_new_booking_reaches_every_linked_teammate(
        tools, store, tenant, tomorrow, confirmed_ctx):
    """Владелец и администратор с привязанным чатом получают запись каждый."""
    tenant.integration.setdefault("handoff", {})["telegramBotToken"] = "тестовый"
    boss = _staff(store, "boss@salon.dev", "111", role="owner")
    taylor = _staff(store, "taylor@salon.dev", "222")

    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(
        service_id="haircut", master_id="alex", start=slot["start"],
        customer_name="Jordan", phone="+598 91234567",
        confirmation_token=slot["token"], ctx=confirmed_ctx)

    tasks = _tasks(store, made["booking_id"])
    for user, chat in ((boss, "111"), (taylor, "222")):
        task = tasks[f"booking-staff-{user.id}-{made['booking_id']}"]
        assert task.audience == "staff" and task.recipient == chat


def test_teammate_who_turned_notifications_off_is_skipped(
        tools, store, tenant, tomorrow, confirmed_ctx):
    tenant.integration.setdefault("handoff", {})["telegramBotToken"] = "тестовый"
    quiet = _staff(store, "quiet@salon.dev", "333", notify=False)
    gone = _staff(store, "gone@salon.dev", "444", active=False)

    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(
        service_id="haircut", master_id="alex", start=slot["start"],
        customer_name="Jordan", phone="+598 91234567",
        confirmation_token=slot["token"], ctx=confirmed_ctx)

    names = set(_tasks(store, made["booking_id"]))
    assert f"booking-staff-{quiet.id}-{made['booking_id']}" not in names
    assert f"booking-staff-{gone.id}-{made['booking_id']}" not in names


def test_owner_chat_is_not_notified_twice(tools, store, tenant, tomorrow, confirmed_ctx):
    """Один чат — одно сообщение, даже если он и канал владельца, и сотрудник."""
    tenant.integration.setdefault("handoff", {})["telegramBotToken"] = "тестовый"
    tenant.integration["handoff"]["telegramChatId"] = "555"
    tenant.integration.setdefault("notifications", {})["ownerProvider"] = "telegram"
    _staff(store, "boss@salon.dev", "555", role="owner")

    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(
        service_id="haircut", master_id="alex", start=slot["start"],
        customer_name="Jordan", phone="+598 91234567",
        confirmation_token=slot["token"], ctx=confirmed_ctx)

    to_555 = [t for t in _tasks(store, made["booking_id"]).values() if t.recipient == "555"]
    assert len(to_555) == 1, to_555


def test_owner_task_is_skipped_without_a_recipient(tools, store, tenant, tomorrow, confirmed_ctx):
    """Канал владельца без получателя — вечный `failed` на каждой записи."""
    tenant.integration["handoff"]["adminWhatsapp"] = ""
    tenant.integration.setdefault("notifications", {})["ownerPhone"] = ""

    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(
        service_id="haircut", master_id="alex", start=slot["start"],
        customer_name="Jordan", phone="+598 91234567",
        confirmation_token=slot["token"], ctx=confirmed_ctx)

    assert f"booking-owner-{made['booking_id']}" not in _tasks(store, made["booking_id"])


def test_delivery_failure_reaches_the_team_in_telegram(
        store, notifications, tenant, booking, monkeypatch):
    """О недоставке клиенту узнают все свои, а не только канал владельца."""
    # Воркер берёт бизнес из реестра, а не фикстурный объект: это разные
    # экземпляры, и правка «в памяти теста» до отправки не доезжает.
    from backend.app.tenants import registry
    live = registry.get(tenant.slug)
    live.integration.setdefault("handoff", {})["telegramBotToken"] = "тестовый"
    # Без SMS-резерва: пока он есть, сбой WhatsApp сначала уходит в дубль по SMS,
    # и до предупреждения дело не доходит.
    live.integration.setdefault("notifications", {})["smsFallback"] = False
    boss = _staff(store, "boss2@salon.dev", "777", role="owner")

    task = _tasks(store, booking.id)[f"booking-confirmed-{booking.id}"]
    monkeypatch.setattr(providers, "send",
                        _raise(providers.SendError("номер не существует", permanent=True)))
    notifications.run_task(task)

    alerts = [t for t in store.list_notifications(booking_id=booking.id)
              if t.type == "owner_delivery_failed"]
    assert any(t.recipient == "777" and t.channel == "telegram" for t in alerts), alerts
    assert any(f"booking-alert-{boss.id}" in t.notification_id for t in alerts)


def test_user_link_codes_differ_between_people():
    from backend.app.policies import user_link_code
    assert user_link_code(1) != user_link_code(2)
    assert user_link_code(7) == user_link_code(7)


def test_master_without_a_chat_gets_no_task(store, booking):
    """Неподключённый мастер не должен плодить `failed` на каждой записи."""
    assert f"booking-master-{booking.id}" not in _tasks(store, booking.id)


def test_master_with_a_chat_is_notified_about_his_own_booking(
        tools, store, tenant, notifications, tomorrow, confirmed_ctx):
    tenant.salon["masters"][0]["telegramChatId"] = "555000"
    tenant.integration.setdefault("handoff", {})["telegramBotToken"] = "тестовый"

    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(
        service_id="haircut", master_id="alex", start=slot["start"],
        customer_name="Jordan", phone="+598 91234567",
        confirmation_token=slot["token"], ctx=confirmed_ctx,
    )
    task = _tasks(store, made["booking_id"])[f"booking-master-{made['booking_id']}"]
    assert task.audience == "master"
    assert task.provider == "telegram" and task.channel == "telegram"
    assert task.recipient == "555000"


def test_master_notification_names_the_client_not_the_master(tenant, booking):
    """Мастеру нужен телефон клиента, а не собственное имя в тексте."""
    text = templates.message_for("master_new_booking", booking, tenant)
    assert "Jordan" in text and "+598" in text
    assert "Alex" not in text


def test_master_is_told_that_a_slot_freed_up(tenant, booking):
    text = templates.message_for("master_booking_cancelled", booking, tenant)
    assert "Отмена" in text and "освободилось" in text


def test_master_link_codes_differ_between_masters_and_salons():
    """Код различает мастеров — иначе двоим уедут чужие записи."""
    from backend.app.policies import master_link_code
    assert master_link_code("demo-salon", "sam") != master_link_code("demo-salon", "marat")
    assert master_link_code("demo-salon", "sam") != master_link_code("second-demo", "sam")
    assert master_link_code("demo-salon", "sam") == master_link_code("demo-salon", "sam")


def test_whatsapp_template_variables_follow_the_approved_order(tenant, booking):
    """Переменные утверждённого шаблона идут подряд и означают то, что написано.

    Twilio нумерует ContentVariables по порядку значений, а Meta не разрешает
    пропуски в {{1}}, {{2}}, {{3}}. Пока сюда уезжали все переменные записи,
    в шаблон «Hola {{1}}, tu cita para {{2}}» вместо услуги подставлялся телефон.
    """
    values = templates.content_variables("booking_confirmation", booking, tenant)
    assert list(values) == ["name", "service", "date", "time", "address"]
    assert values["name"] == "Jordan"
    assert values["service"] == "Стрижка"
    assert "@" not in values["service"] and "+" not in values["service"]


def test_spanish_message_carries_no_russian_text(tenant, booking):
    """Испанскому клиенту — испанский текст, испанское название и испанская дата.

    Имя клиента и адрес салона остаются как есть: их не переводят, а
    воспроизводят. Проверяем то, что действительно должно смениться языком.
    """
    tenant.salon["services"][0]["titleEs"] = "Corte de dama"
    text = templates.message_for("booking_confirmation", booking, tenant, {}, "es")
    assert "Corte de dama" in text          # название услуги
    # Месяц по-испански — «6 sep», а не «6 сен». Берём его из самой записи:
    # прибитый к тексту «ago» ломал тест каждый сентябрь.
    month = MONTHS["es"][_aware(booking.start_at).astimezone(zone(tenant.timezone)).month - 1]
    assert month in text
    assert "Стрижка" not in text
    assert "Ваша запись" not in text and "подтверждена" not in text


def test_untranslated_service_falls_back_to_the_main_title(tenant, booking):
    """Пустой перевод — «пока не перевели», а не пустое место в сообщении."""
    tenant.salon["services"][0]["titleEs"] = ""
    assert "Стрижка" in templates.message_for("booking_confirmation", booking, tenant, {}, "es")


def test_owner_template_from_the_form_survives_translation(tenant, booking):
    """Свой текст владельца не подменяется готовым переводом."""
    mine = "Su cita: {{service}}, {{time}}."
    text = templates.message_for("booking_confirmation", booking, tenant,
                                 {"booking_confirmation": mine}, "es")
    assert text.startswith("Su cita:")


def test_unknown_template_sends_no_variables(tenant, booking):
    """Чужому шаблону лучше уйти обычным текстом, чем со случайными подстановками."""
    assert templates.content_variables("нет-такого-шаблона", booking, tenant) == {}


def test_default_texts_use_exactly_the_declared_variables():
    """Текст на `console` и утверждённый WhatsApp-шаблон должны совпадать.

    Проверка боем идёт на `console`: если готовый текст использует не тот набор
    переменных, что объявлен для шаблона, владелец утверждает в Meta одно, а
    видит при проверке другое.
    """
    import re
    for lang, texts in templates.LOCALIZED_TEMPLATES.items():
        for kind, text in texts.items():
            used = set(re.findall(r"\{\{\s*(\w+)\s*\}\}", text))
            # Личная ссылка есть не у каждого текста: у переноса её нет. Всё
            # остальное обязано совпадать с объявленным набором.
            declared = set(templates.variables_order(kind, manage_button="link" in used))
            assert used == declared, (lang, kind, used)


def test_texts_mention_variables_in_the_approved_order():
    """Порядок переменных в тексте — тот же, что в нумерации шаблона.

    Twilio нумерует значения по порядку, а Meta отклоняет шаблон, где {{3}}
    стоит раньше {{2}}. Русское «сегодня в 18:00 у вас запись на стрижку»
    читается лучше испанского порядка — и именно поэтому такой текст нельзя
    отдать в шаблон, не переставив слова.
    """
    import re

    for lang, texts in [("ru", templates.DEFAULT_TEMPLATES),
                        *templates.LOCALIZED_TEMPLATES.items()]:
        for kind, text in texts.items():
            used = list(dict.fromkeys(re.findall(r"\{\{\s*(\w+)\s*\}\}", text)))
            order = templates.variables_order(kind, manage_button="link" in used)
            if not order:
                continue
            assert used == [k for k in order if k in used], (lang, kind, used, order)


def test_client_gets_messages_in_the_language_of_the_booking(tenant, store, notifications, tomorrow):
    """Записался по-русски — и подтверждение с напоминаниями придут по-русски.

    Язык салона стоял в настройках и молча перекрывал язык клиента: человек
    писал боту по-русски, а получал испанский текст со своим именем.
    """
    booking = store.create_booking(
        tenant_id=tenant.slug, master_id="alex", service_id="haircut",
        start_at=now(tenant.timezone).replace(hour=12, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
        end_at=now(tenant.timezone).replace(hour=13, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
        client_name="Лиза", phone="+59891234567", client_id="cl-ru", lang="ru",
    )
    tasks = {t.type: t for t in notifications.schedule_for_booking(booking, tenant)
             if t.audience == "client"}
    assert tasks, "клиентских задач не поставлено"
    for kind, task in tasks.items():
        assert task.lang == "ru", (kind, task.lang)



def test_message_carries_the_short_address(tenant, booking):
    """В сообщении — улица с домом, а не почтовый адрес целиком.

    Половина строки на индекс и департамент — это то, что клиент и так знает,
    а в напоминании он ищет глазами номер дома.
    """
    tenant.salon["address"] = "100 Example Street, Example City"
    values = templates.variables_for(booking, tenant, "es")
    assert values["address"] == "100 Example Street"

    # Свой короткий адрес сильнее обрезки: запятая стоит не везде, где надо.
    tenant.salon["addressShort"] = "Local 5, Galería del Sol"
    assert templates.variables_for(booking, tenant, "es")["address"] == "Local 5, Galería del Sol"

    # Полный адрес остаётся при салоне — им пользуются карты и страница записи.
    assert tenant.salon["address"].endswith("Example City")


def test_link_form_follows_the_template_text(tenant, store, notifications, tomorrow,
                                             monkeypatch):
    """Полный адрес или хвост для кнопки — решает текст шаблона, а не настройка.

    Настройка это уже решала, и не пережила панель: поля `manageLinkInText` нет
    в `config/schema.json`, любое сохранение формы вычищало его из
    `integration.json` — и клиенты получали «Cambiar o cancelar:
    e0333b26…?tenant=demo-salon», хвост без домена. Теперь источник один: стоит
    `{{link}}` в тексте — уезжает полный адрес, нет — только хвост для кнопки.
    """
    from backend.app.notify import templates as tpl
    from backend.app.notify.service import settings_for

    booking = store.create_booking(
        tenant_id=tenant.slug, master_id="alex", service_id="haircut",
        start_at=now(tenant.timezone).replace(hour=12, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
        end_at=now(tenant.timezone).replace(hour=13, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
        client_name="Lucía", phone="+59891234567", client_id="cl-link", lang="es",
    )
    tenant.integration["notifications"] = {**tenant.integration["notifications"],
                                           "manageButtonTemplates": True}
    s = settings_for(tenant)
    tasks = [t for t in notifications.schedule_for_booking(booking, tenant)
             if t.audience == "client" and t.type in
             ("booking_confirmation", "booking_reminder_day_before", "booking_reminder_today")]
    assert tasks

    for task in tasks:
        # Живое поколение шаблонов — с кнопкой: в её адрес Meta пускает только
        # окончание, начало зашито в самом шаблоне.
        assert not tpl.link_in_body(task.type, "es"), task.type
        values = notifications.template_variables(task, booking, tenant, s, "es")
        assert values["link"].startswith("cl-link?"), (task.type, values["link"])

        # Текст без ссылки внутри — значит на `console`, в SMS и в Telegram её
        # приписывает отдельная строка, и ровно один раз.
        body = notifications.client_body(task, booking, tenant, s, "es")
        assert "Cambiar o cancelar: https://" in body, (task.type, body)
        assert body.count("/manage/cl-link") == 1, body

    # Вернули ссылку в текст шаблона — вместе с ней возвращается и полный адрес.
    with_link = {**tpl.LOCALIZED_TEMPLATES["es"]}
    with_link["booking_confirmation"] = (
        "¡Hola, {{name}}! Su cita para {{service}} está confirmada: {{date}} a las "
        "{{time}}. Lo esperamos en {{address}}. Cambiar o cancelar: {{link}} ¡Hasta pronto!")
    monkeypatch.setitem(tpl.LOCALIZED_TEMPLATES, "es", with_link)
    task = next(t for t in tasks if t.type == "booking_confirmation")
    values = notifications.template_variables(task, booking, tenant, s, "es")
    assert values["link"].startswith("http")
    assert "/manage/cl-link" in values["link"]
    body = notifications.client_body(task, booking, tenant, s, "es")
    assert body.count("/manage/cl-link") == 1, body


def test_message_stays_readable_without_a_link(tenant, booking):
    """Нет ссылки — нет и обещания её дать.

    У записи без карточки клиента ссылки не существует, и «Перенести или
    отменить:» повисало бы двоеточием в пустоту.
    """
    text = templates.message_for("booking_confirmation", booking, tenant, {}, "es", link="")
    assert "Cambiar o cancelar" not in text
    assert text.endswith("¡Hasta pronto!")


def test_manage_button_adds_the_link_as_the_last_variable(tenant, booking):
    """Кнопка «Перенести или отменить» — это ещё одна переменная, и она последняя.

    Meta разрешает подставлять в адрес кнопки только его окончание, поэтому хвост
    личной ссылки уезжает обычной переменной. Встань она не в конец — кнопка
    поведёт на чужую запись, а в текст подставится токен.
    """
    without = templates.content_variables("booking_confirmation", booking, tenant)
    assert "link" not in without

    with_button = templates.content_variables("booking_confirmation", booking, tenant,
                                              manage_button=True)
    assert list(with_button) == ["name", "service", "date", "time", "address", "link"]
    assert list(templates.variables_order("booking_reminder_today", manage_button=True)) == [
        "name", "service", "time", "address", "link"]

    # Просьба об оценке и предложение места несут свою ссылку с самого начала —
    # флаг их набор не трогает.
    assert templates.variables_order("review_request", manage_button=True) == (
        "name", "salon", "service", "link")


def test_manage_button_off_keeps_the_approved_variable_count(tenant, store, notifications, booking):
    """Пока Meta не одобрила шаблон с кнопкой, лишняя переменная не уходит.

    У утверждённого шаблона строго пять переменных: шестая отбивается Twilio
    (63028), и клиент не получает ни подтверждения, ни напоминания.
    """
    from backend.app.notify.service import settings_for

    settings = settings_for(tenant)
    assert settings.manage_button is False
    task = next(t for t in store.list_notifications(booking_id=booking.id)
                if t.type == "booking_confirmation")
    values = notifications.template_variables(task, booking, tenant, settings, "es")
    assert list(values) == ["name", "service", "date", "time", "address"]

    tenant.integration["notifications"] = {**tenant.integration["notifications"],
                                           "manageButtonTemplates": True}
    settings = settings_for(tenant)
    values = notifications.template_variables(task, booking, tenant, settings, "es")
    assert list(values) == ["name", "service", "date", "time", "address", "link"]
    assert values["link"].startswith(booking.client_id)
    assert "token=" in values["link"] and "lang=es" in values["link"]


def test_reschedule_goes_as_an_approved_template(tenant, store, notifications, booking, monkeypatch):
    """Подтверждение переноса уходит утверждённым шаблоном, а не свободным текстом.

    Свободный текст Meta пропускает только сутки после сообщения клиента, а
    клиент из виджета салону не писал никогда: о новом времени он не узнавал.
    Шаблон бескнопочный, поэтому шестая переменная ему не положена даже при
    включённой кнопке — иначе Twilio отобьёт отправку кодом 63028.
    """
    from backend.app.notify.service import settings_for

    live = _twilio_tenant(tenant.slug, contentSidRescheduled="HX-перенос",
                          manageButtonTemplates=True)
    settings = settings_for(live)
    assert settings.manage_button is True
    assert settings.provider_cfg("twilio")["contentSids"]["booking_rescheduled"] == "HX-перенос"

    task = next(t for t in store.list_notifications(booking_id=booking.id)
                if t.type == "booking_confirmation")
    task.type = "booking_rescheduled"
    values = notifications.template_variables(task, booking, live, settings, "es")
    assert list(values) == ["name", "service", "date", "time", "address"]


def test_every_template_name_declares_its_variables():
    """Новый тип уведомления обязан объявить порядок переменных явно."""
    assert set(templates.TEMPLATE_NAMES) == set(templates.TEMPLATE_VARIABLES)


def _raise(exc):
    def _send(**_kwargs):
        raise exc
    return _send


# --- телефон клиента ----------------------------------------------------------

def test_local_number_becomes_international():
    """«099000101» + Уругвай → «+59899000101».

    Клиент вводит номер так, как набирает дома. Twilio отвечал «The 'To' number
    +099000101 is not a valid phone number», и подтверждение не уходило вовсе.
    """
    from backend.app.policies import to_international

    assert to_international("099 000 101", "598") == "+59899000101"
    assert to_international("099000101", "+598") == "+59899000101"


def test_number_with_country_code_is_left_alone():
    from backend.app.policies import to_international

    assert to_international("+598 99 000 101", "598") == "+59899000101"
    assert to_international("59899000101", "598") == "+59899000101"


def test_without_country_setting_number_is_not_guessed():
    """Угадывать страну по длине — однажды отправить сообщение не туда."""
    from backend.app.policies import to_international

    assert to_international("099000101", "") == "+099000101"


def test_foreign_number_does_not_get_the_local_country_code():
    """«+7 999 123 45 67» остаётся российским, а не становится уругвайским.

    В базе телефон лежит цифрами, без «+», и `to_international` вызывается на
    сохранённом значении ещё раз — для получателя уведомления, для телефона в
    сообщении мастеру, для ключа карточки. Российские «79991234567» превращались
    при этом в «+59879991234567»: подтверждение уходило чужому человеку в
    Монтевидео, а клиент не получал ничего.
    """
    from backend.app.policies import client_key, to_international

    assert to_international("+7 999 123 45 67", "598") == "+79991234567"
    # Так этот номер лежит в карточке и в записи — цифрами, «+» уже потерян.
    assert to_international("79991234567", "598") == "+79991234567"
    assert to_international("5491123456789", "598") == "+5491123456789"
    # Ключ карточки от этого становится устойчивым: как ввели, так и найдётся.
    assert client_key("+7 999 123 45 67", "598") == client_key("79991234567", "598")

    # Местный номер по-прежнему получает код страны — в любом написании.
    assert to_international("99000101", "598") == "+59899000101"
    assert to_international("099000101", "598") == "+59899000101"


def test_foreign_number_without_a_plus_is_still_refused():
    """Домашний формат чужой страны без «+» — по-прежнему отказ на входе.

    Иначе «11 2345 6789» из Буэнос-Айреса молча стало бы чьим-то номером: ни
    угадать страну по длине, ни оставить как есть тут нельзя.
    """
    from backend.app.policies import phone_problem

    assert phone_problem("1123456789", "598") == "need_country_code"
    assert phone_problem("+54 11 2345 6789", "598") == ""
    assert phone_problem("1234567", "598") == "bad_phone"


def test_client_task_gets_an_international_recipient(
        tools, store, tenant, tomorrow, confirmed_ctx):
    """В очередь получатель попадает уже в E.164 — провайдеру иначе не отдать."""
    tenant.salon["phoneCountry"] = "598"
    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(service_id="haircut", master_id="alex", start=slot["start"],
                                customer_name="Ana", phone="099000101",
                                confirmation_token=slot["token"], ctx=confirmed_ctx)

    task = _tasks(store, made["booking_id"])[f"booking-confirmed-{made['booking_id']}"]
    assert task.recipient == "+59899000101"


def test_foreign_client_task_keeps_its_own_country_code(
        tools, store, tenant, tomorrow, confirmed_ctx):
    """Запись с российского номера — и получатель в очереди российский.

    Путь длиннее, чем кажется: номер уезжает в карточку и в запись цифрами, без
    «+», и `to_international` вызывается на этом сохранённом значении. Пока код
    страны приписывался механически, в очередь попадал «+59879991234567» —
    Twilio отбивал такое сообщение, и клиент не получал ничего. На проде так
    лежали двое: польский +48 и российский +7.
    """
    tenant.salon["phoneCountry"] = "598"
    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(service_id="haircut", master_id="alex", start=slot["start"],
                                customer_name="Ирина", phone="+7 926 559 38 75",
                                confirmation_token=slot["token"], ctx=confirmed_ctx)

    task = _tasks(store, made["booking_id"])[f"booking-confirmed-{made['booking_id']}"]
    assert task.recipient == "+79265593875"

    # И в самом сообщении — тоже свой код страны: мастер звонит по нему нажатием.
    booking = store.get_booking(made["booking_id"], tenant_id=tenant.slug)
    assert templates.variables_for(booking, tenant, "ru")["phone"] == "+79265593875"


def test_sms_fallback_is_skipped_without_a_sender(store, notifications, tenant, booking, monkeypatch):
    """Без купленного SMS-номера резерв только плодит `failed`."""
    from backend.app.tenants import registry
    live = registry.get(tenant.slug)          # воркер берёт бизнес отсюда
    live.integration.setdefault("notifications", {}).update(
        {"provider": "twilio", "smsFallback": True, "twilioSmsFrom": ""})
    task = _tasks(store, booking.id)[f"booking-confirmed-{booking.id}"]
    monkeypatch.setattr(providers, "send",
                        _raise(providers.SendError("нет доставки", permanent=True)))
    notifications.run_task(task)

    assert not [t for t in store.list_notifications(booking_id=booking.id)
                if t.channel == "sms"]


def test_confirmation_and_reminders_carry_the_manage_link(tenant, store, notifications, tomorrow):
    """Под подтверждением и напоминанием — личная ссылка на свои записи.

    Без неё «перенести или отменить» упирается в переписку с администратором:
    клиент отвечает на сообщение, и кто-то должен это прочитать руками.
    """
    from backend.app.notify.service import settings_for

    booking = store.create_booking(
        tenant_id=tenant.slug, master_id="alex", service_id="haircut",
        start_at=now(tenant.timezone).replace(hour=12, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
        end_at=now(tenant.timezone).replace(hour=13, minute=0, second=0, microsecond=0)
        + timedelta(days=1),
        client_name="Lucía", phone="+59891234567", client_id="cl-1", lang="es",
    )
    tasks = notifications.schedule_for_booking(booking, tenant)
    settings = settings_for(tenant)

    kinds = {"booking_confirmation", "booking_reminder_day_before", "booking_reminder_today"}
    seen = set()
    for task in tasks:
        if task.type not in kinds:
            continue
        seen.add(task.type)
        body = notifications.client_body(task, booking, tenant, settings, settings.language)
        assert "/manage/cl-1" in body, (task.type, body)
        assert "token=" in body, (task.type, body)
    assert "booking_confirmation" in seen

    # Владельцу личная ссылка клиента не нужна и не уходит.
    owner = next(t for t in tasks if t.audience == "owner")
    assert "/manage/" not in notifications.client_body(owner, booking, tenant, settings, "ru")


def test_message_without_a_booking_does_not_crash_the_worker(tenant, store, notifications):
    """Рассылка и предложение места уходят без записи — и не роняют очередь.

    Такие задачи несут готовый текст, записи у них нет. Пока «нет записи»
    обозначалось истиной, дальше по коду она уходила в сборку шаблона —
    `True.start_at` валило воркер на каждом предложении освободившегося места
    и на каждой рассылке, то есть на обеих фичах удержания разом.
    """
    from datetime import datetime, timezone

    for kind, name in (("waitlist_offer", "waitlist-offer-1"), ("campaign", "campaign-1")):
        assert store.enqueue_notification(
            notification_id=name, tenant_id=tenant.slug, booking_id="", type=kind,
            audience="client", provider="console", channel="whatsapp",
            recipient="+59891234567", body="Освободилось место. Забрать: https://booking.test/x",
            scheduled_at=datetime.now(timezone.utc)) is not None

    due = store.claim_due_notifications(datetime.now(timezone.utc), limit=10)
    assert {t.type for t in due} == {"waitlist_offer", "campaign"}
    assert [notifications.run_task(task) for task in due] == ["sent", "sent"]


def test_client_reply_reaches_the_team(store, notifications, tenant):
    """Ответ клиента в WhatsApp доходит до людей, а не теряется.

    В шаблонах написано «ответьте на это сообщение» — значит ответ обязан
    куда-то приходить.
    """
    tenant.integration.setdefault("handoff", {})["telegramBotToken"] = "тестовый"
    boss = _staff(store, "boss@salon.dev", "111", role="owner")
    assert boss

    sent = notifications.notify_staff_client_reply(
        tenant, "+59899000102", "Можно перенести на завтра?", client_name="Jordan")

    assert sent == 1
    task = next(t for t in store.list_notifications(tenant_id=tenant.slug)
                if t.type == "owner_client_reply")
    assert task.channel == "telegram" and task.recipient == "111"
    assert "Можно перенести на завтра?" in task.body
    assert "Jordan" in task.body


def test_client_reply_without_telegram_is_reported_not_lost(store, notifications, tenant):
    """Без подключённого бота ответ доставить некуда — говорим это честно."""
    tenant.integration.setdefault("handoff", {})["telegramBotToken"] = ""

    assert notifications.notify_staff_client_reply(tenant, "+59899000102", "Привет") == 0


def test_client_reply_task_survives_the_guard(store, notifications, tenant):
    """У ответа клиента нет записи — guard не должен отменять такую задачу."""
    tenant.integration.setdefault("handoff", {})["telegramBotToken"] = "тестовый"
    _staff(store, "boss@salon.dev", "111", role="owner")
    notifications.notify_staff_client_reply(tenant, "+59899000102", "Спасибо!")

    task = next(t for t in store.list_notifications(tenant_id=tenant.slug)
                if t.type == "owner_client_reply")
    booking, reason = notifications.guard(task)
    assert (booking, reason) == (None, None)


# --- просьба об оценке и предложение места: утверждённый шаблон ----------------

def _twilio_tenant(slug: str, **notifications_cfg):
    """Живой бизнес из реестра с настроенным Twilio — воркер берёт его отсюда."""
    from backend.app.tenants import registry
    live = registry.get(slug)
    live.integration.setdefault("notifications", {}).update({
        "provider": "twilio", "clientChannel": "whatsapp", "language": "es",
        "twilioAccountSid": "AC-тест", "twilioAuthToken": "секрет",
        "twilioWhatsappFrom": "+59899000103", **notifications_cfg,
    })
    return live


def _recorder(monkeypatch):
    """Подменяет отправку и запоминает, с чем её позвали."""
    calls: list[dict] = []

    def fake_send(**kwargs):
        calls.append(kwargs)
        return providers.SendResult("SM-тест")

    monkeypatch.setattr(notify_service.providers, "send", fake_send)
    return calls


def _visit(store, tenant, hour: int, lang: str = "es"):
    """Завершённый визит сегодня в указанный час по времени салона."""
    start = now(tenant.timezone).replace(hour=hour, minute=0, second=0, microsecond=0)
    return store.create_booking(
        tenant_id=tenant.slug, master_id="alex", service_id="haircut",
        start_at=start, end_at=start + timedelta(hours=1),
        client_name="Lucía", phone="+59891234567", client_id="cl-7", lang=lang,
    )


def test_review_request_goes_as_an_approved_template(store, notifications, tenant, monkeypatch):
    """Просьба об оценке уходит шаблоном на языке клиента, а не свободным текстом.

    Свободный текст Meta пропускает только в 24-часовом окне, а клиент из
    виджета салону не писал никогда: без шаблона просьба падала с `63016`.
    """
    # Воркер берёт бизнес из реестра, а не фикстурный объект: настраиваем тот,
    # с которым он и будет работать.
    live = _twilio_tenant(tenant.slug, contentSidReviewEs="HX-es", contentSidReviewRu="HX-ru")
    booking = _visit(store, live, hour=12, lang="ru")
    task = notifications.schedule_review(booking, live)
    assert task is not None and task.type == "review_request" and task.lang == "ru"

    calls = _recorder(monkeypatch)
    assert notifications.run_task(task) == "sent"

    sent = calls[0]
    assert sent["cfg"]["contentSids"]["review_request"] == "HX-ru"
    # Порядок переменных — контракт с утверждённым шаблоном.
    assert list(sent["variables"]) == ["name", "salon", "service", "link"]
    # В кнопку уезжает только хвост адреса: начало зашито в сам шаблон.
    assert "tenant=" in sent["variables"]["link"] and "token=" in sent["variables"]["link"]
    assert not sent["variables"]["link"].startswith("http")


def test_review_template_falls_back_to_the_language_of_the_salon(
        store, notifications, tenant, monkeypatch):
    """Нет шаблона на языке клиента — берём язык салона, а не молчим.

    Испанский текст с рабочей кнопкой полезнее английского, которого Meta не
    пропустит: клиент хотя бы попадёт в форму.
    """
    live = _twilio_tenant(tenant.slug, contentSidReviewEs="HX-es")
    booking = _visit(store, live, hour=12, lang="en")
    task = notifications.schedule_review(booking, live)

    calls = _recorder(monkeypatch)
    notifications.run_task(task)
    assert calls[0]["cfg"]["contentSids"]["review_request"] == "HX-es"


def test_review_is_asked_a_couple_of_hours_after_the_visit(store, notifications, tenant):
    """Через пару часов после визита, пока клиент ещё помнит, как всё прошло."""
    from backend.app.notify.service import review_time, settings_for

    settings = settings_for(tenant)
    booking = _visit(store, tenant, hour=12)
    when = review_time(booking, tenant, settings,
                       now=_aware(booking.end_at)).astimezone(zone(tenant.timezone))
    assert (when.hour, when.minute) == (15, 0)   # визит 12:00–13:00 плюс два часа


def test_review_is_not_asked_at_night(store, notifications, tenant):
    """Поздний визит — просьба уходит утром, а не в полночь."""
    from backend.app.notify.service import review_time, settings_for

    settings = settings_for(tenant)
    booking = _visit(store, tenant, hour=20)     # конец в 21:00, плюс два часа — 23:00
    when = review_time(booking, tenant, settings,
                       now=_aware(booking.end_at)).astimezone(zone(tenant.timezone))
    assert (when.hour, when.minute) == (9, 0)
    assert when.date() > _aware(booking.end_at).astimezone(zone(tenant.timezone)).date()


def test_waitlist_offer_carries_its_template_variables(
        store, notifications, tenant, tools, tomorrow, confirmed_ctx, monkeypatch):
    """Предложение места тоже уходит шаблоном — со своими переменными."""
    live = _twilio_tenant(tenant.slug, contentSidWaitlistEs="HX-wait-es")
    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(service_id="haircut", master_id="alex", start=slot["start"],
                                customer_name="Ana", phone="+59891112233",
                                confirmation_token=slot["token"], ctx=confirmed_ctx)
    booking = store.get_booking(made["booking_id"], tenant_id=tenant.slug)

    client = store.upsert_client(tenant_id=tenant.slug, phone="+59899000101",
                                 name="Lucía", lang="es", consent=True)
    date_key = templates.local_date_key(_aware(booking.start_at), tenant.timezone)
    store.add_waitlist(tenant_id=tenant.slug, client_id=client.id, service_id="haircut",
                       master_id="", date_from=date_key, date_to=date_key,
                       time_from="", time_to="")

    assert notifications.offer_waitlist(booking, live) == 1
    task = next(t for t in store.list_notifications(tenant_id=tenant.slug)
                if t.type == "waitlist_offer")
    assert task.lang == "es"

    calls = _recorder(monkeypatch)
    notifications.run_task(task)
    sent = calls[0]
    assert list(sent["variables"]) == ["name", "service", "date", "time", "link"]
    assert sent["variables"]["name"] == "Lucía"
    assert sent["cfg"]["contentSids"]["waitlist_offer"] == "HX-wait-es"


def test_sms_fallback_keeps_the_text_of_a_message_without_a_booking(
        store, notifications, tenant, monkeypatch):
    """Дубль по SMS уносит готовый текст с собой.

    У просьбы об оценке записи нет — собрать текст заново в момент отправки
    неоткуда, и SMS уходил пустым: Twilio отвечал «Body required», а клиент не
    получал ничего ни по одному каналу.
    """
    live = _twilio_tenant(tenant.slug, smsFallback=True, twilioSmsFrom="+59899000103")
    booking = _visit(store, live, hour=12, lang="es")
    task = notifications.schedule_review(booking, live)

    monkeypatch.setattr(notify_service.providers, "send",
                        _raise(providers.SendError("номер не существует", permanent=True)))
    notifications.run_task(task)

    sms = next(t for t in store.list_notifications(tenant_id=tenant.slug) if t.channel == "sms")
    assert sms.body == task.body and sms.lang == "es" and sms.variables == task.variables


def test_reschedule_tells_the_master_and_the_owner(tools, store, tenant, tomorrow, confirmed_ctx):
    """Перенос — такое же изменение рабочего дня, как новая запись.

    Раньше о нём узнавал только клиент: мастер продолжал ждать к прежнему часу,
    а владелец видел перемену, лишь заглянув в журнал.
    """
    tenant.salon["masters"][0]["telegramChatId"] = "555000"
    tenant.integration.setdefault("handoff", {})["telegramBotToken"] = "тестовый"
    tenant.integration["policies"]["allowReschedule"] = True

    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    day = slots["availability"][0]["days"][0]["slots"]
    made = tools.create_booking(
        service_id="haircut", master_id="alex", start=day[0]["start"],
        customer_name="Jordan", phone="+598 91234567",
        confirmation_token=day[0]["token"], ctx=confirmed_ctx)
    moved = tools.reschedule_booking(
        booking_id=made["booking_id"], master_id="alex", start=day[2]["start"],
        confirmation_token=day[2]["token"], ctx=confirmed_ctx)

    tasks = [t for t in _tasks(store, moved["booking_id"]).values() if t.status == "scheduled"]
    kinds = {t.type for t in tasks}
    assert "master_booking_rescheduled" in kinds
    assert "owner_booking_rescheduled" in kinds
    assert "booking_rescheduled" in kinds       # клиенту — как и раньше
    master_task = next(t for t in tasks if t.type == "master_booking_rescheduled")
    assert master_task.recipient == "555000" and master_task.channel == "telegram"


def test_old_master_learns_the_booking_left_him(tools, store, tenant, tomorrow, confirmed_ctx):
    """Смена мастера: прежнему пишем про его прежнее время, а не про новое."""
    tenant.salon["masters"][0]["telegramChatId"] = "111"
    tenant.salon["masters"][1]["telegramChatId"] = "222"
    tenant.integration.setdefault("handoff", {})["telegramBotToken"] = "тестовый"
    tenant.integration["policies"]["allowReschedule"] = True

    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    day = slots["availability"][0]["days"][0]["slots"]
    made = tools.create_booking(
        service_id="haircut", master_id="alex", start=day[0]["start"],
        customer_name="Jordan", phone="+598 91234567",
        confirmation_token=day[0]["token"], ctx=confirmed_ctx)
    was_time = made["time"]
    tools.reschedule_booking(
        booking_id=made["booking_id"], master_id="taylor", start=day[2]["start"],
        confirmation_token=slot_token("taylor", "haircut", day[2]["start"], tenant.slug),
        ctx=confirmed_ctx)

    tasks = _tasks(store, made["booking_id"])
    left = [t for t in tasks.values() if t.recipient == "111" and t.status == "scheduled"]
    assert left and "ушла к другому мастеру" in left[0].body
    assert was_time in left[0].body            # его прежнее время, а не новое
    assert any(t.recipient == "222" for t in tasks.values() if t.status == "scheduled")


def test_client_is_told_when_the_salon_cancels(tools, store, tenant, tomorrow, confirmed_ctx):
    """Отменяет салон — приходит клиент. Без этого сообщения он узнаёт у двери."""
    slots = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow)
    slot = slots["availability"][0]["days"][0]["slots"][0]
    made = tools.create_booking(
        service_id="haircut", master_id="alex", start=slot["start"],
        customer_name="Jordan", phone="+598 91234567",
        confirmation_token=slot["token"], ctx=confirmed_ctx)
    booking = store.get_booking(made["booking_id"], tenant_id=tenant.slug)

    store.set_booking_status(booking.id, "cancelled", tenant_id=tenant.slug)
    notify = notify_service.NotificationService(store)
    notify.cancel_for_booking(booking.id, "cancelled_by_admin")
    task = notify.notify_client_cancelled(booking, tenant)

    assert task is not None and task.type == "booking_cancelled"
    assert task.audience == "client" and task.status == "scheduled"
    # Задача пережила снятие остальных: её ставят после `cancel_for_booking`.
    assert task.notification_id in _tasks(store, booking.id)


def test_cancelled_booking_lets_its_own_message_through(store, tenant, booking):
    """Guard снимает задачи по отменённой записи — кроме сообщения об отмене."""
    notify = notify_service.NotificationService(store)
    notify.cancel_for_booking(booking.id, "cancelled_by_admin")
    store.set_booking_status(booking.id, "cancelled", tenant_id=tenant.slug)
    task = notify.notify_client_cancelled(booking, tenant)

    passed, reason = notify.guard(task)
    assert reason is None and passed is not None

    same_day = _tasks(store, booking.id)[f"booking-reminder-same-day-{booking.id}"]
    _, why = notify.guard(same_day)
    assert why == "статус записи: cancelled"


def test_past_visit_gets_no_cancellation_message(store, tenant, booking):
    """«Ваша запись отменена» назавтра после визита — недоумение, а не забота."""
    from datetime import timedelta as _td

    store.set_booking_status(booking.id, "cancelled", tenant_id=tenant.slug)
    booking.start_at = datetime.now(timezone.utc) - _td(hours=3)
    notify = notify_service.NotificationService(store)
    assert notify.notify_client_cancelled(booking, tenant) is None


def test_cancellation_text_names_the_visit_without_address(tenant, booking):
    text = templates.message_for("booking_cancelled", booking, tenant)
    assert "отменена" in text and "Jordan" in text
    assert tenant.salon["address"] not in text        # звать по адресу отменённого незачем
    assert not text.rstrip().endswith("}}")           # Meta не пускает переменную в конце
