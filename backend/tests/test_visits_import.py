"""Импорт истории визитов: переезд салона из чужой системы.

Главное, что здесь проверяется, — импорт молчит: ни одной задачи в очереди
уведомлений. Всё остальное — про то, что метрики клиента после переезда
совпадают с файлом.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.app import visits_csv
from backend.tests.conftest import write_tenant

HEAD = "Имя,Телефон,Дата,Время,Услуга,Мастер,Сумма,Статус"


def _day(offset: int) -> str:
    """Дата в прошлом: history — это визиты, которые уже были."""
    return (datetime.now() - timedelta(days=offset)).strftime("%d.%m.%Y")


def _file(*rows: str) -> str:
    return "\n".join((HEAD, *rows))


def _post(client, text: str, *, commit: bool = False):
    return client.post("/api/admin/visits/import", json={"csv": text, "commit": commit})


@pytest.fixture
def history() -> str:
    return _file(
        f"Jordan,+598 91234567,{_day(30)},11:00,Стрижка,Alex,900,выполнена",
        f"Jordan,091 234 567,{_day(10)},12:00,Окрашивание,Alex,2500,выполнена",
        f"Мария,+598 99887766,{_day(5)},13:00,Стрижка,Taylor,1200,не пришёл",
    )


def test_preview_writes_nothing(client, history):
    report = _post(client, history).json()

    assert report["total"] == 3
    assert report["created"] == 3
    assert report["rejected"] == 0
    assert report["committed"] is False
    assert client.get("/api/admin/bookings").json()["bookings"] == []
    assert client.get("/api/admin/clients").json()["clients"] == []


def test_import_creates_history_and_metrics(client, history):
    report = _post(client, history, commit=True).json()
    assert (report["created"], report["rejected"]) == (3, 0)

    bookings = client.get("/api/admin/bookings").json()["bookings"]
    assert len(bookings) == 3
    assert {b["source"] for b in bookings} == {"import"}

    people = {c["phone"]: c for c in client.get("/api/admin/clients").json()["clients"]}
    # Два номера одного человека — «091 234 567» и «+598 91234567» — сходятся
    # в одну карточку тем же ключом, что и при обычной записи.
    assert len(people) == 2
    jordan = people["59891234567"]
    assert (jordan["visits"], jordan["ltv"]) == (2, 3400)
    assert jordan["lastVisitAt"]

    maria = people["59899887766"]
    assert (maria["visits"], maria["noShows"], maria["ltv"]) == (0, 1, 0)


def test_import_queues_no_notifications(client, history):
    """Самое важное: переезд не должен разослать напоминания о прошлых визитах."""
    _post(client, history, commit=True)

    assert client.get("/api/notifications").json()["notifications"] == []


def test_repeat_import_creates_nothing(client, history):
    first = _post(client, history, commit=True).json()
    # Предпросмотр второго захода уже показывает, что нового нет.
    preview = _post(client, history).json()
    second = _post(client, history, commit=True).json()

    assert first["created"] == 3
    assert (preview["created"], preview["rejected"]) == (0, 3)
    assert second["created"] == 0
    assert second["rejected"] == 3
    assert all("уже есть в базе" in row["reason"] for row in second["rows"])
    assert len(client.get("/api/admin/bookings").json()["bookings"]) == 3


def test_broken_rows_rejected_with_reason(client):
    text = _file(
        f"Без телефона,,{_day(3)},11:00,Стрижка,Alex,900,выполнена",
        f"Короткий,123,{_day(3)},12:00,Стрижка,Alex,900,выполнена",
        "Без даты,+598 91111111,не дата,13:00,Стрижка,Alex,900,выполнена",
        f"Без времени,+598 92222222,{_day(3)},,Стрижка,Alex,900,выполнена",
        f"Чужая услуга,+598 93333333,{_day(3)},14:00,Массаж,Alex,900,выполнена",
        f"Чужой мастер,+598 94444444,{_day(3)},15:00,Стрижка,Пётр,900,выполнена",
    )
    report = _post(client, text, commit=True).json()

    assert (report["created"], report["rejected"]) == (0, 6)
    reasons = [row["reason"] for row in report["rows"]]
    assert reasons == ["нет телефона", "телефон не похож на настоящий", "не разобрали дату",
                       "не разобрали время визита", "услуга не найдена: Массаж",
                       "мастер не найден: Пётр"]
    # Несопоставленные названия собраны отдельно: их сопоставляют руками.
    assert report["unmatched"] == {"services": ["Массаж"], "masters": ["Пётр"]}
    assert client.get("/api/admin/bookings").json()["bookings"] == []


def test_duplicate_inside_file(client):
    same = _day(4)
    text = _file(
        f"Jordan,+598 91234567,{same},11:00,Стрижка,Alex,900,выполнена",
        f"Другой,+598 99887766,{same},11:00,Стрижка,Alex,900,выполнена",
    )
    report = _post(client, text, commit=True).json()

    assert (report["created"], report["rejected"]) == (1, 1)
    assert "уже есть в файле" in report["rows"][0]["reason"]


def test_semicolon_bom_and_foreign_money(client):
    """Так выгружает Excel в русской и испанской локали."""
    text = ("﻿Nombre;Teléfono;Fecha;Hora;Servicio;Profesional;Importe;Estado\n"
            f"Jordan;+598 91234567;{_day(7)};11:00;Стрижка;Alex;$ 1.200,50;atendido")
    report = _post(client, text, commit=True).json()

    assert (report["created"], report["rejected"]) == (1, 0)
    booking = client.get("/api/admin/bookings").json()["bookings"][0]
    assert booking["paidAmount"] == 1200
    assert client.get("/api/admin/clients").json()["clients"][0]["ltv"] == 1200


def test_file_without_time_column_rejected(client):
    text = ("Имя,Телефон,Дата,Услуга,Мастер\n"
            f"Jordan,+598 91234567,{_day(3)},Стрижка,Alex")
    response = _post(client, text)

    assert response.status_code == 400
    assert "время визита" in response.json()["detail"]


def test_other_tenant_sees_nothing(client, tenants_dir, history):
    write_tenant(tenants_dir, "otro")
    _post(client, history, commit=True)

    assert client.get("/api/admin/bookings", params={"tenant": "otro"}).json()["bookings"] == []
    assert client.get("/api/admin/clients", params={"tenant": "otro"}).json()["clients"] == []


def test_solo_master_needs_no_columns(tenant):
    """У частного мастера в выгрузке нет колонок «услуга» и «мастер» — выбора нет."""
    tenant.salon["masters"] = tenant.salon["masters"][:1]
    tenant.salon["services"] = tenant.salon["services"][:1]

    rows, missing = visits_csv.parse(
        f"Имя,Телефон,Дата,Время\nJordan,+598 91234567,{_day(3)},11:00",
        tenant=tenant, country="598")

    assert missing == []
    assert (rows[0].action, rows[0].service_id, rows[0].master_id) == ("created", "haircut", "alex")


@pytest.mark.parametrize(("text", "expected"), [
    ("2026-03-04", "2026-03-04"),
    ("04.03.2026", "2026-03-04"),
    ("04/03/2026", "2026-03-04"),
    ("4.3.26", "2026-03-04"),
    # Американский файл выдаёт себя вторым числом больше двенадцати.
    ("03/25/2026", "2026-03-25"),
    ("31.02.2026", ""),             # 31 февраля не бывает
    ("вчера", ""),
])
def test_dates_are_day_first(text, expected):
    assert visits_csv._date(text) == expected


@pytest.mark.parametrize(("text", "expected"), [
    ("900", 900), ("1 200", 1200), ("$ 1.200,50", 1200), ("1,200.00", 1200),
    ("2500 UYU", 2500), ("", 0), ("бесплатно", 0),
])
def test_money_in_any_notation(text, expected):
    assert visits_csv._money(text) == expected
