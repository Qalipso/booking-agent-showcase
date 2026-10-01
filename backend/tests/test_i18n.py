"""Язык клиента: подписи дат и язык ответа агента приходят из запроса."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.timeutil import human_date, norm_lang
from backend.tests.conftest import write_tenant


@pytest.fixture
def client(tenants_dir, tmp_path, monkeypatch):
    from backend.app import deps
    from backend.app.db import Store

    write_tenant(tenants_dir, "demo-salon")
    monkeypatch.setenv("ADMIN_ALLOW_NO_TOKEN", "1")
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'i18n.db'}"))

    from backend.app.main import app

    return TestClient(app)


def test_human_date_per_language():
    assert human_date("2026-08-06") == "чт, 6 авг"
    assert human_date("2026-08-06", "es") == "jue, 6 ago"
    assert human_date("2026-08-06", "en") == "Thu, Aug 6"


def test_unknown_language_falls_back_to_russian():
    assert norm_lang("de") == "ru"
    assert norm_lang(None) == "ru"
    assert norm_lang("ES-uy") == "es"


def test_days_labels_follow_lang(client):
    ru = client.get("/api/days", params={"masterId": "alex", "tenant": "demo-salon"}).json()["days"]
    en = client.get("/api/days", params={"masterId": "alex", "tenant": "demo-salon", "lang": "en"}).json()["days"]
    es = client.get("/api/days", params={"masterId": "alex", "tenant": "demo-salon", "lang": "es"}).json()["days"]

    assert ru and en and es
    assert [d["date"] for d in ru] == [d["date"] for d in en] == [d["date"] for d in es]
    assert ru[0]["label"] == "сегодня"
    assert en[0]["label"] == "today"
    assert es[0]["label"] == "hoy"


def test_system_prompt_language_overrides_tenant_setting():
    from backend.app.agent import build_system_prompt
    from backend.app.deps import runtime

    rt = runtime.for_tenant("demo-salon")
    assert "Responde en español." in build_system_prompt(rt.tenant, rt.tools, "es")
    assert "Answer in English." in build_system_prompt(rt.tenant, rt.tools, "en")
    # Неизвестный код не ломает промпт — остаётся язык из настроек салона.
    assert "Отвечай по-русски." in build_system_prompt(rt.tenant, rt.tools, "de")


def test_service_titles_follow_lang(tenants_dir, tmp_path, monkeypatch):
    """Каталог виджета отдаётся на языке клиента, непереведённое — как есть."""
    import copy

    from backend.app import deps
    from backend.app.db import Store
    from backend.tests.conftest import SALON

    salon = copy.deepcopy(SALON)
    salon["services"][0].update({"titleEs": "Corte de pelo", "titleEn": "Haircut",
                                 "desc": "Авторская стрижка", "descEn": "Signature haircut"})
    write_tenant(tenants_dir, "demo-salon", salon=salon)
    monkeypatch.setenv("ADMIN_ALLOW_NO_TOKEN", "1")
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'i18n-services.db'}"))

    from backend.app.main import app

    client = TestClient(app)
    by_lang = {}
    for lang in ("ru", "es", "en"):
        services = client.get(f"/api/config?lang={lang}").json()["services"]
        by_lang[lang] = {s["id"]: s for s in services}

    assert by_lang["ru"]["haircut"]["title"] == "Стрижка"
    assert by_lang["es"]["haircut"]["title"] == "Corte de pelo"
    assert by_lang["en"]["haircut"]["title"] == "Haircut"
    # Описание переведено только на английский — испанец видит основной текст.
    assert by_lang["es"]["haircut"]["desc"] == "Авторская стрижка"
    assert by_lang["en"]["haircut"]["desc"] == "Signature haircut"
    # Услуга без переводов остаётся на основном языке во всех запросах.
    assert {by_lang[l]["color"]["title"] for l in by_lang} == {"Окрашивание"}


def test_saving_config_keeps_translations_and_upsells(tenants_dir, tmp_path, monkeypatch):
    """Форма сохраняет переводы и допродажи, а не вычищает их при нормализации."""
    from backend.app import deps
    from backend.app.db import Store

    write_tenant(tenants_dir, "demo-salon")
    monkeypatch.setenv("ADMIN_ALLOW_NO_TOKEN", "1")
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'i18n-save.db'}"))

    from backend.app.main import app

    client = TestClient(app)
    payload = client.get("/api/admin/config?tenant=demo-salon").json()["data"]
    payload["services"][0].update({"titleEn": "Haircut", "suggestWith": ["color"]})
    assert client.put("/api/admin/config?tenant=demo-salon", json=payload).status_code == 200

    saved = client.get("/api/admin/config?tenant=demo-salon").json()["data"]["services"][0]
    assert saved["titleEn"] == "Haircut"
    assert saved["suggestWith"] == ["color"]


def test_master_role_and_price_follow_lang(tenants_dir, tmp_path, monkeypatch):
    """Специализация мастера и цена — тоже текст для клиента, а не служебные поля."""
    import copy

    from backend.app import deps
    from backend.app.db import Store
    from backend.tests.conftest import SALON

    salon = copy.deepcopy(SALON)
    salon["masters"][0].update({"roleEs": "Corte y color", "roleEn": "Cuts and colour"})
    salon["services"][0].update({"price": "900 UYU (скидка 20%)",
                                 "priceEs": "900 UYU (20% de descuento)"})
    write_tenant(tenants_dir, "demo-salon", salon=salon)
    monkeypatch.setenv("ADMIN_ALLOW_NO_TOKEN", "1")
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'i18n-roles.db'}"))

    from backend.app.main import app

    client = TestClient(app)
    es = client.get("/api/config?lang=es").json()
    en = client.get("/api/config?lang=en").json()
    ru = client.get("/api/config?lang=ru").json()

    assert {m["id"]: m["role"] for m in es["masters"]}["alex"] == "Corte y color"
    assert {m["id"]: m["role"] for m in en["masters"]}["alex"] == "Cuts and colour"
    assert {m["id"]: m["role"] for m in ru["masters"]}["alex"] == "Hair and color"
    # Мастер без перевода остаётся на основном языке — пустой подписи быть не должно.
    assert {m["id"]: m["role"] for m in es["masters"]}["taylor"] == "Стрижка"
    assert {s["id"]: s["price"] for s in es["services"]}["haircut"] == "900 UYU (20% de descuento)"
    # Английского перевода нет — показываем цену как есть, а не пустоту.
    assert {s["id"]: s["price"] for s in en["services"]}["haircut"] == "900 UYU (скидка 20%)"


def test_model_catalog_has_no_russian_for_spanish_client(tools):
    """Каталог в промпте — на языке клиента: модель пересказывает его дословно."""
    tools.tenant.masters[0].update({"roleEs": "Corte y color"})
    tools.tenant.services[0].update({"titleEs": "Corte de pelo"})

    catalog = tools.catalog("es")

    assert {m["id"]: m["role"] for m in catalog["masters"]}["alex"] == "Corte y color"
    assert {s["id"]: s["title"] for s in catalog["services"]}["haircut"] == "Corte de pelo"


def test_handoff_message_follows_client_language(tools):
    """Русский текст владельца не уходит испанке — ей нужен испанский."""
    from backend.app.tools import ToolContext

    es = tools.handoff_to_human(reason="test", ctx=ToolContext(conversation_id="c1", history=[], lang="es"))
    ru = tools.handoff_to_human(reason="test", ctx=ToolContext(conversation_id="c2", history=[], lang="ru"))

    assert es["message"] == "Le paso su consulta al administrador — se comunicarán con usted en breve."
    # По-русски остаётся текст, который владелец написал сам.
    assert ru["message"] == "Передаю администратору."


def test_handoff_uses_owner_translation_when_it_exists(tenant, store, notifications):
    """Заполненный перевод важнее нашего текста: салон пишет своё."""
    from backend.app.calendar_service import CalendarService
    from backend.app.policies import RateLimiter
    from backend.app.tools import BookingTools, ToolContext

    tenant.integration["handoff"]["handoffMessageEs"] = "Le escribe el administrador."
    tools = BookingTools(tenant, store, CalendarService(tenant, store), RateLimiter(), notifications)

    out = tools.handoff_to_human(reason="test", ctx=ToolContext(conversation_id="c", history=[], lang="es"))

    assert out["message"] == "Le escribe el administrador."


def test_booking_page_defaults_to_business_language(tenants_dir, tmp_path, monkeypatch):
    """Ссылку из шапки Instagram открывает клиент салона, а не мы."""
    import copy

    from backend.app import deps
    from backend.app.db import Store
    from backend.tests.conftest import INTEGRATION

    integration = copy.deepcopy(INTEGRATION)
    # Как на проде: язык бота «auto», язык уведомлений клиенту — испанский.
    integration["ai"] = {**integration["ai"], "language": "auto"}
    integration["notifications"] = {**integration["notifications"], "language": "es"}
    write_tenant(tenants_dir, "demo-salon", integration=integration)
    monkeypatch.setenv("ADMIN_ALLOW_NO_TOKEN", "1")
    deps.runtime.bind(Store(f"sqlite:///{tmp_path/'i18n-book.db'}"))

    from backend.app.main import app

    client = TestClient(app)
    page = client.get("/book/demo-salon").text

    assert '<html lang="es">' in page
    assert "reserva en línea" in page
    # Явный запрос сильнее умолчания.
    assert '<html lang="en">' in client.get("/book/demo-salon?lang=en").text


def test_booking_refusal_carries_a_code_for_the_widget(client, tomorrow):
    """Отказ приходит с кодом: русский текст сервера испанке показывать нельзя."""
    ok = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": "12:00",
        "name": "Ана", "phone": "099000101", "lang": "es",
    })
    assert ok.status_code == 200, ok.text

    clash = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": "12:00",
        "name": "Мария", "phone": "092122030", "lang": "es",
    })
    assert clash.status_code == 409
    assert clash.json()["detail"]["code"] == "slot_taken"

    promo = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": "13:30",
        "name": "Мария", "phone": "092122030", "lang": "es", "promoCode": "НЕТ-ТАКОГО",
    })
    assert promo.status_code == 400
    assert promo.json()["detail"]["code"] == "promo_unknown"
