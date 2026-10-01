"""События бизнеса в логах.

Логи легко ломаются молча: строку убрали при рефакторинге, и никто не заметил,
пока не понадобилось ответить, сколько записей сорвалось вчера. Поэтому ключевые
события проверяются так же, как ответы API.
"""

from __future__ import annotations

import logging


def _events(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "event"]


def test_booking_created_is_logged(client, tomorrow, caplog):
    with caplog.at_level(logging.INFO, logger="event"):
        slot = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                                "date": tomorrow}).json()["slots"][0]
        res = client.post("/api/book", json={
            "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slot["time"],
            "name": "Jordan", "phone": "+598 91234567", "token": slot["token"],
        })
    assert res.status_code == 200, res.text

    line = next(m for m in _events(caplog) if m.startswith("event=booking.created"))
    assert "master=alex" in line
    assert "service=haircut" in line
    assert f"booking={res.json()['bookingId']}" in line
    # Телефон и имя в поток событий не уходят: их место в базе, а не в логах.
    assert "91234567" not in line
    assert "Jordan" not in line


def test_refusal_names_the_reason(client, tomorrow, caplog):
    """Отказ пишет код причины — иначе в журнале остаётся голый «400»."""
    with caplog.at_level(logging.INFO, logger="event"):
        res = client.post("/api/book", json={
            "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": "12:00",
            "name": "Jordan", "phone": "+598 91234567", "token": "подделка",
        })
    assert res.status_code == 400

    line = next(m for m in _events(caplog) if m.startswith("event=booking.refused"))
    assert "status=400" in line
    assert "reason=" in line


def test_cancellation_is_logged(client, tomorrow, caplog):
    slot = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                            "date": tomorrow}).json()["slots"][0]
    booking_id = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slot["time"],
        "name": "Jordan", "phone": "+598 91234567", "token": slot["token"],
    }).json()["bookingId"]

    with caplog.at_level(logging.INFO, logger="event"):
        assert client.post(f"/api/admin/bookings/{booking_id}/status",
                           json={"status": "cancelled"}).status_code == 200

    line = next(m for m in _events(caplog) if m.startswith("event=booking.status"))
    assert "status=cancelled" in line
    assert f"booking={booking_id}" in line


def test_payment_is_logged(client, tomorrow, caplog):
    slot = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                            "date": tomorrow}).json()["slots"][0]
    booking_id = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slot["time"],
        "name": "Jordan", "phone": "+598 91234567", "token": slot["token"],
    }).json()["bookingId"]

    with caplog.at_level(logging.INFO, logger="event"):
        assert client.patch(f"/api/admin/bookings/{booking_id}/payment",
                            json={"paidAmount": 900, "paymentMethod": "cash"}).status_code == 200

    line = next(m for m in _events(caplog) if m.startswith("event=payment.saved"))
    assert "method=cash" in line
    assert "amount=900" in line


def test_values_with_spaces_stay_one_field():
    """Причина отказа — фраза с пробелами: без кавычек парсер увидел бы мусор."""
    from backend.app.events import _fmt

    assert _fmt("нет мест") == '"нет мест"'
    assert _fmt("slot_taken") == "slot_taken"
    assert _fmt(None) == "—"
    # Кавычка внутри значения ломала бы разбор строки на поля.
    assert '"' not in _fmt('он сказал "нет"')[1:-1]


def test_identifier_survives_the_pii_filter():
    """Маскировка телефонов не должна портить идентификаторы.

    Внутри 32-символьного id легко набирается восемь цифр подряд, и фильтр
    принимал их за номер: в логах оставалось «cf0eddebacaf4c+***ba5f7e822e»,
    по которому запись уже не найти.
    """
    from backend.app.policies import mask_pii

    assert mask_pii("booking=cf0eddebacaf4c17965538ba5f7e822e") == (
        "booking=cf0eddebacaf4c17965538ba5f7e822e")
    # Настоящий номер по-прежнему затирается — в любом написании.
    assert "91234567" not in mask_pii("клиент +598 91234567")
    assert "099000101" not in mask_pii("тел 099000101")
    assert "91234567" not in mask_pii("→ +598 91234567: текст")
