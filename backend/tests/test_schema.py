"""Схема конфигурации: валидация, маскирование секретов, экспорт в .env."""

from __future__ import annotations

import copy

from backend.app.schema import MASK, SCHEMA, to_env, to_files, to_form, validate_config
from backend.tests.conftest import INTEGRATION, SALON


def form_payload() -> dict:
    form = to_form(copy.deepcopy(SALON), copy.deepcopy(INTEGRATION))
    return form


def test_valid_config_passes():
    assert validate_config(form_payload()) == []


def test_required_fields_reported():
    data = form_payload()
    data["salon"]["name"] = ""
    errors = validate_config(data)
    assert any("Название" in e for e in errors)


def test_service_longer_than_workday_rejected():
    data = form_payload()
    data["services"][0]["duration"] = 600
    assert any("длиннее рабочего дня" in e for e in validate_config(data))


def test_master_day_outside_salon_schedule():
    data = form_payload()
    data["salon"]["workDays"] = [1, 2, 3, 4, 5]
    assert any("вне графика салона" in e for e in validate_config(data))


def test_master_shift_outside_salon_hours_rejected():
    """Смена за пределами часов салона просто не даёт слотов — говорим об этом в форме."""
    data = form_payload()
    data["masters"][0]["workHours"] = {"start": "09:00", "end": "23:00"}
    errors = validate_config(data)
    assert any("раньше открытия" in e for e in errors), errors
    assert any("позже закрытия" in e for e in errors), errors


def test_master_shift_end_before_start_rejected():
    data = form_payload()
    data["masters"][0]["workHours"] = {"start": "18:00", "end": "12:00"}
    assert any("позже начала" in e for e in validate_config(data))


def test_empty_master_shift_is_valid():
    """Пустая смена — «как у салона», это нормальное значение."""
    data = form_payload()
    data["masters"][0]["workHours"] = {"start": "", "end": ""}
    assert validate_config(data) == []


def test_master_shift_survives_a_form_save():
    """Жёсткий словарь мастеров в `to_files` уже терял поля — проверяем явно."""
    data = form_payload()
    data["masters"][0]["workHours"] = {"start": "14:00", "end": "18:00"}
    salon, _ = to_files(data, copy.deepcopy(INTEGRATION))
    assert salon["masters"][0]["workHours"] == {"start": "14:00", "end": "18:00"}


def test_master_shift_hours_are_not_editable_by_the_form():
    """Часы смены форма настроек не показывает и не трогает.

    Их задаёт отдельный экран, а `to_files` собирает мастера строго по схеме:
    убери поле из схемы совсем — и первое же сохранение формы вычистит часы
    из salon.json. Поэтому поле остаётся, но помечено `managedOutsideForm`,
    и для уже существующего мастера файл авторитетнее снимка формы.
    """
    masters = next(s for s in SCHEMA["sections"] if s["id"] == "masters")
    fields = {f["key"]: f for f in masters["fields"]}
    for key in ("workHours.start", "workHours.end"):
        assert fields[key]["type"] == "hidden", key
        assert fields[key]["managedOutsideForm"] is True, key

    saved = copy.deepcopy(SALON)
    saved["masters"][0]["workHours"] = {"start": "12:00", "end": "16:00"}

    # Панель прислала устаревший снимок — часы в нём другие. Побеждает файл.
    data = form_payload()
    data["masters"][0]["workHours"] = {"start": "09:00", "end": "23:00"}
    salon, _ = to_files(data, copy.deepcopy(INTEGRATION), previous_salon=saved)
    assert salon["masters"][0]["workHours"] == {"start": "12:00", "end": "16:00"}


def test_review_link_survives_a_form_save():
    """Ссылку «оставить отзыв» сохранение настроек не стирает.

    `to_files` собирает salon.json строго по схеме, и ключа `googleMapsUrl` в
    ней сначала не было: поле читал бэкенд отзывов, документация его описывала,
    а первое же автосохранение формы вычищало его из файла — молча, потому что
    валидацию это не нарушает. Тест держит поле в схеме.
    """
    salon = copy.deepcopy(SALON)
    salon["googleMapsUrl"] = "https://g.page/r/demo-salon/review"

    form = to_form(salon, copy.deepcopy(INTEGRATION))
    assert form["salon"]["googleMapsUrl"] == "https://g.page/r/demo-salon/review"
    assert validate_config(form) == []

    saved, _ = to_files(form, copy.deepcopy(INTEGRATION), previous_salon=salon)
    assert saved["googleMapsUrl"] == "https://g.page/r/demo-salon/review"


def test_form_data_does_not_alias_the_live_config():
    """Форма — копия, а не ссылка на конфиг арендатора.

    Списки мастеров и услуг раньше отдавались тем же объектом, что живёт в
    `tenant.salon`. Правка формы в памяти переписывала настройки мимо
    валидации и записи на диск, а поля с `managedOutsideForm` теряли смысл:
    «прежнее значение из файла» и «присланное формой» оказывались одним
    словарём, и сравнивать было не с чем.
    """
    salon = copy.deepcopy(SALON)
    form = to_form(salon, copy.deepcopy(INTEGRATION))

    form["masters"][0]["workHours"] = {"start": "07:00", "end": "08:00"}
    form["services"][0]["title"] = "Подменённое название"

    assert salon["masters"][0].get("workHours") != {"start": "07:00", "end": "08:00"}
    assert salon["services"][0]["title"] != "Подменённое название"


def test_ai_without_key_is_not_a_form_error():
    """Ключ проверяет карточка подключения, а не форма.

    Прежнее правило «включено — значит нужен ключ» запирало сохранение всей
    панели, когда `enabled` в файле бизнеса расходился с ключом в окружении.
    """
    data = form_payload()
    data["ai"] = {"enabled": True, "model": "gpt-4.1-mini", "provider": "groq"}
    assert validate_config(data) == []


def test_ai_with_key_is_valid():
    """Ключ на месте — раздел AI больше ничего не требует."""
    data = form_payload()
    data["ai"] = {"enabled": True, "model": "gpt-4.1-mini", "provider": "openai", "apiKey": "k"}
    assert validate_config(data) == []


def test_whatsapp_needs_credentials():
    data = form_payload()
    data["channel"] = {"kind": "whatsapp"}
    assert any("WhatsApp" in e for e in validate_config(data))


def test_owner_telegram_without_chat_rejected():
    """Провайдер telegram без chatId — молчащий канал, а не рабочая настройка."""
    data = form_payload()
    data["notificationsInternal"]["ownerProvider"] = "telegram"
    data["handoff"]["telegramChatId"] = ""
    assert any("чат не привязан" in e for e in validate_config(data))


def test_owner_telegram_with_chat_passes():
    data = form_payload()
    data["notificationsInternal"]["ownerProvider"] = "telegram"
    data["handoff"]["telegramChatId"] = "-1001234567890"
    assert validate_config(data) == []


def test_owner_email_requires_recipient_and_smtp_settings():
    data = form_payload()
    data["notificationsInternal"].update({"ownerProvider": "email"})
    data["handoff"]["adminEmail"] = ""
    errors = validate_config(data)
    assert any("email администратора" in e for e in errors), errors
    assert any("SMTP host" in e for e in errors), errors

    data["handoff"]["adminEmail"] = "owner@example.com"
    data["notificationsInternal"].update({
        "smtpHost": "smtp.example.com", "smtpPort": 587,
        "smtpSecurity": "starttls", "smtpFrom": "bot@example.com",
    })
    assert validate_config(data) == []


def test_untouched_owner_provider_does_not_lock_the_form():
    """Дефолт не должен требовать Telegram: бизнес, который его не подключал,
    обязан сохраняться. Раньше на этом запиралась вся панель."""
    data = form_payload()
    data["notifications"].pop("ownerProvider", None)
    assert validate_config(data) == []


def test_disabled_notifications_skip_owner_checks():
    data = form_payload()
    data["notifications"]["enabled"] = False
    data["notificationsInternal"]["ownerProvider"] = "telegram"
    data["handoff"]["telegramChatId"] = ""
    assert validate_config(data) == []


def test_twilio_credentials_are_checked_across_screens():
    """Креды Twilio живут на «Каналах связи», а провайдер — на «Клиентских».

    Правило про недостающий номер должно срабатывать всё равно: экраны разные,
    секция файла одна.
    """
    data = form_payload()
    data["notifications"].update({"enabled": True, "provider": "twilio", "clientChannel": "whatsapp"})
    data["notificationsTwilio"] = {"twilioWhatsappFrom": "", "twilioSmsFrom": ""}
    errors = validate_config(data)
    assert any("WhatsApp-номер Twilio" in e for e in errors), errors

    data["notificationsTwilio"]["twilioWhatsappFrom"] = "+15005550006"
    data["notifications"]["smsFallback"] = True
    assert any("SMS-номер Twilio" in e for e in validate_config(data))


def test_duplicate_ids_rejected():
    data = form_payload()
    data["masters"][1]["id"] = data["masters"][0]["id"]
    assert any("уникальны" in e for e in validate_config(data))


def test_secrets_never_reach_form_or_files():
    """Секреты живут в окружении и в базе, а не в форме и не в JSON."""
    integration = copy.deepcopy(INTEGRATION)
    vault: dict[str, str] = {"handoff.telegramBotToken": "real-secret"}

    form = to_form(copy.deepcopy(SALON), integration, vault.__contains__)
    assert form["handoff"]["telegramBotToken"] == MASK  # наружу отдаём только маску

    # Сохранение маски секрет не затирает: значение в форму и не приходило.
    _, saved = to_files(form, integration, on_secret=vault.__setitem__)
    assert "telegramBotToken" not in saved["handoff"]
    assert vault["handoff.telegramBotToken"] == "real-secret"


def test_empty_value_does_not_wipe_a_saved_secret():
    """Панель, открытая до подключения, не должна стирать ключи автосохранением.

    Ровно так пропадал только что подключённый Twilio: страница держала поля
    пустыми, автосохранение отправляло «», и ключи затирались.
    """
    form = form_payload()
    form["handoff"] = {**form.get("handoff", {}), "telegramBotToken": ""}
    vault: dict[str, str] = {"handoff.telegramBotToken": "живой-токен"}

    to_files(form, copy.deepcopy(INTEGRATION), on_secret=vault.__setitem__)
    assert vault["handoff.telegramBotToken"] == "живой-токен"


def test_new_secret_goes_to_store_not_to_file():
    form = form_payload()
    form["handoff"] = {**form.get("handoff", {}), "telegramBotToken": "fresh-token"}
    vault: dict[str, str] = {}

    _, saved = to_files(form, copy.deepcopy(INTEGRATION), on_secret=vault.__setitem__)
    assert vault["handoff.telegramBotToken"] == "fresh-token"
    assert "telegramBotToken" not in saved["handoff"]


def test_env_export_contains_policies_but_no_secret_values():
    integration = copy.deepcopy(INTEGRATION)
    integration["handoff"]["telegramBotToken"] = "real-secret"
    env = to_env(integration, "demo-salon")
    assert "REQUIRE_CONFIRMATION=true" in env
    assert "IDEMPOTENCY_ENABLED=true" in env
    assert "MAX_BOOKINGS_PER_PHONE_PER_DAY=3" in env
    # Раньше этот файл уезжал в репозиторий вместе с токеном.
    assert "real-secret" not in env
    assert "DEMO_SALON_TELEGRAM_BOT_TOKEN" in env


def test_roundtrip_keeps_masters_and_services():
    form = form_payload()
    salon, _ = to_files(form, copy.deepcopy(INTEGRATION))
    assert [m["id"] for m in salon["masters"]] == [m["id"] for m in SALON["masters"]]
    assert [s["id"] for s in salon["services"]] == [s["id"] for s in SALON["services"]]


def test_new_list_field_from_schema_survives_without_serializer_change(monkeypatch):
    """Новое поле схемы не требует четвёртого ручного патча в `to_files`."""
    services = next(s for s in SCHEMA["sections"] if s["id"] == "services")
    fields = [*services["fields"], {"key": "futureField", "label": "Будущее", "type": "text"}]
    monkeypatch.setitem(services, "fields", fields)
    form = form_payload()
    form["services"][0]["futureField"] = "не потерять"

    salon, _ = to_files(form, copy.deepcopy(INTEGRATION))

    assert salon["services"][0]["futureField"] == "не потерять"


def test_missing_bool_keeps_its_default():
    """Поле, которого нет в форме, не должно тихо выключаться.

    Панель, открытая до появления поля в схеме, присылает конфигурацию без
    него — и любое сохранение гасило умолчание. Так «бот работает сам»
    превратился в false, и бот снова начал обещать звонок администратора.
    """
    data = form_payload()
    data["handoff"].pop("autonomous", None)
    _salon, integration = to_files(data)
    assert integration["handoff"]["autonomous"] is True, integration["handoff"]


def test_explicit_false_is_still_respected():
    data = form_payload()
    data["handoff"]["autonomous"] = False
    _salon, integration = to_files(data)
    assert integration["handoff"]["autonomous"] is False


def test_stale_form_does_not_unlink_a_master():
    """Панель, открытая до привязки, не должна отвязывать мастера.

    Чат ставит кнопка, форма его не показывает и присылает пустым — и первое же
    сохранение настроек молча лишало мастера уведомлений.
    """
    salon = copy.deepcopy(SALON)
    salon["masters"][0]["telegramChatId"] = "555000"

    form = to_form(copy.deepcopy(SALON), copy.deepcopy(INTEGRATION))   # снимок без чата
    saved, _ = to_files(form, copy.deepcopy(INTEGRATION), previous_salon=salon)
    assert saved["masters"][0]["telegramChatId"] == "555000"


def test_outside_managed_field_uses_latest_file_not_stale_form():
    """Скрытое поле из старой вкладки не перезаписывает отдельный endpoint."""
    salon = copy.deepcopy(SALON)
    salon["masters"][0]["telegramChatId"] = "новый"

    form = to_form(copy.deepcopy(SALON), copy.deepcopy(INTEGRATION))
    form["masters"][0]["telegramChatId"] = "старый снимок"
    saved, _ = to_files(form, copy.deepcopy(INTEGRATION), previous_salon=salon)
    assert saved["masters"][0]["telegramChatId"] == "новый"


def test_stale_form_does_not_overwrite_latest_master_shifts():
    salon = copy.deepcopy(SALON)
    salon["masters"][0]["shifts"] = {"2026-09-02": {"off": True}}
    form = to_form(copy.deepcopy(SALON), copy.deepcopy(INTEGRATION))
    form["masters"][0]["shifts"] = {"2026-09-01": {"off": True}}

    saved, _ = to_files(form, copy.deepcopy(INTEGRATION), previous_salon=salon)

    assert saved["masters"][0]["shifts"] == {"2026-09-02": {"off": True}}
