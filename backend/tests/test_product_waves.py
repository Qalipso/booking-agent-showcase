"""Сквозные проверки продуктовых волн: от публичной записи до отчёта."""

from __future__ import annotations

from datetime import datetime

from backend.app.policies import signed_action


def _configure_money(client):
    data = client.get("/api/admin/config").json()["data"]
    data["services"][0]["priceAmount"] = 1000
    data["services"][0]["currency"] = "UYU"
    data["salon"]["loyaltyEnabled"] = True
    data["salon"]["loyaltyPercent"] = 5
    data["promotions"] = [{
        "code": "HOLA10", "kind": "percent", "value": 10,
        "firstVisitOnly": True, "active": True,
    }]
    assert client.put("/api/admin/config", json=data).status_code == 200


def _book(client, tomorrow, *, master="alex", phone="+598 91234567", promo=""):
    slot = client.get("/api/slots", params={
        "masterId": master, "serviceId": "haircut", "date": tomorrow,
    }).json()["slots"][0]
    response = client.post("/api/book", json={
        "masterId": master, "serviceId": "haircut", "date": tomorrow,
        "time": slot["time"], "name": "Jordan", "phone": phone,
        "token": slot["token"], "promoCode": promo, "source": "instagram", "lang": "es",
    })
    assert response.status_code == 200, response.text
    return response.json()["bookingId"], slot


def test_promo_creates_client_and_money_report(client, tomorrow):
    _configure_money(client)
    booking_id, _ = _book(client, tomorrow, promo="hola10")

    booking = next(x for x in client.get("/api/admin/bookings").json()["bookings"]
                   if x["id"] == booking_id)
    assert booking["priceAmount"] == 1000
    assert booking["discountAmount"] == 100
    assert booking["promoCode"] == "HOLA10"
    assert booking["source"] == "instagram"
    assert booking["lang"] == "es"

    people = client.get("/api/admin/clients").json()["clients"]
    assert people[0]["lang"] == "es"
    assert people[0]["phone"] == "59891234567"

    paid = client.patch(f"/api/admin/bookings/{booking_id}/payment", json={
        "paidAmount": 900, "paymentMethod": "card", "discountAmount": 100,
    })
    assert paid.status_code == 200
    assert client.post(f"/api/admin/bookings/{booking_id}/status", json={"status": "completed"}).status_code == 200
    report = client.get("/api/admin/finance").json()
    assert report["revenue"] == 900
    assert report["averageCheck"] == 900
    assert report["bySource"]["instagram"]["completed"] == 1
    assert report["byPromo"]["HOLA10"]["revenue"] == 900
    assert client.get("/api/admin/clients").json()["clients"][0]["loyalty"] == 45


def test_admin_reschedule_and_public_manage_page(client, tomorrow):
    booking_id, first = _book(client, tomorrow)
    slots = client.get("/api/slots", params={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow,
    }).json()["slots"]
    next_slot = next(x for x in slots if x["time"] != first["time"])
    moved = client.put(f"/api/admin/bookings/{booking_id}/reschedule", json={
        "masterId": "alex", "date": tomorrow, "time": next_slot["time"],
    })
    assert moved.status_code == 200, moved.text
    row = next(x for x in client.get("/api/admin/bookings").json()["bookings"] if x["id"] == booking_id)
    # Время приходит с поясом, поэтому сравниваем момент, а не строку: «15:00»
    # и «15:00+00:00» — одно и то же, но `endswith` этого не знает.
    assert datetime.fromisoformat(row["start"]) == datetime.fromisoformat(next_slot["start"])

    client_id = row["clientId"]
    token = signed_action("manage", "demo-salon", client_id)
    assert client.get(f"/manage/{client_id}", params={"tenant": "demo-salon", "token": token}).status_code == 200
    assert client.post(f"/api/manage/{client_id}/bookings/{booking_id}/confirm",
                       params={"tenant": "demo-salon", "token": token}).json()["confirmed"] is True


def test_reschedule_slots_show_only_free_time_including_its_own(client, tomorrow):
    """Панель переноса спрашивает окна, а не даёт набрать любое время.

    Своё время записи в списке остаётся — от него и двигают. Время соседней
    записи не показывается вовсе: раньше администратор узнавал о занятости
    только из отказа сервера, уже нажав «Перенести».
    """
    booking_id, first = _book(client, tomorrow)
    others = [x for x in client.get("/api/slots", params={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow}).json()["slots"]]
    neighbour = others[1]["time"]
    taken = client.post("/api/admin/bookings", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": neighbour,
        "name": "Мария", "phone": "+598 99112233"})
    assert taken.status_code == 200, taken.text

    windows = client.get(f"/api/admin/bookings/{booking_id}/slots",
                         params={"masterId": "alex", "date": tomorrow})
    assert windows.status_code == 200, windows.text
    times = [s["time"] for s in windows.json()["slots"]]
    assert first["time"] in times            # своё время — точка отсчёта переноса
    assert neighbour not in times            # чужая запись в список не попадает
    assert windows.json()["current"]["time"] == first["time"]


def test_admin_cancel_writes_to_the_client(client, tomorrow):
    """Отмена из панели ставит клиенту сообщение, а не только снимает напоминания."""
    booking_id, _ = _book(client, tomorrow)
    assert client.post(f"/api/admin/bookings/{booking_id}/status",
                       json={"status": "cancelled"}).status_code == 200
    rows = client.get("/api/notifications", params={"booking": booking_id}).json()["notifications"]
    mine = [n for n in rows if n["type"] == "booking_cancelled"]
    assert mine and mine[0]["status"] == "scheduled", rows


def test_waitlist_is_offered_when_slot_is_cancelled(client, tomorrow):
    booking_id, slot = _book(client, tomorrow)
    added = client.post("/api/admin/waitlist", json={
        "name": "Мария", "phone": "+598 99112233", "serviceId": "haircut",
        "masterId": "alex", "dateFrom": tomorrow, "dateTo": tomorrow,
        "timeFrom": slot["time"], "timeTo": slot["time"],
    })
    assert added.status_code == 200
    assert client.post(f"/api/admin/bookings/{booking_id}/status",
                       json={"status": "cancelled"}).status_code == 200
    offered = client.get("/api/admin/waitlist", params={"status": "offered"}).json()["entries"]
    assert [x["id"] for x in offered] == [added.json()["id"]]


def test_completed_visit_creates_review_and_public_page(client, tomorrow):
    booking_id, _ = _book(client, tomorrow)
    assert client.post(f"/api/admin/bookings/{booking_id}/status",
                       json={"status": "completed"}).status_code == 200
    review = client.get("/api/admin/reviews").json()["reviews"][0]
    token = signed_action("review", "demo-salon", review["id"])
    assert client.get(f"/review/{review['id']}", params={
        "tenant": "demo-salon", "token": token,
    }).status_code == 200
    submitted = client.post(f"/api/reviews/{review['id']}", params={
        "tenant": "demo-salon", "token": token,
    }, json={"score": 4, "feedback": "Всё хорошо"})
    assert submitted.status_code == 200
    assert submitted.json()["public"] is False


def test_resource_prevents_two_masters_using_one_chair(client, tomorrow):
    location_id = client.post("/api/admin/locations", json={
        "code": "centro", "name": "Centro", "address": "18 de Julio",
    }).json()["id"]
    assert client.post("/api/admin/resources", json={
        "code": "laser-1", "name": "Аппарат 1", "kind": "laser",
        "locationId": location_id, "capacity": 1,
    }).status_code == 200
    data = client.get("/api/admin/config").json()["data"]
    data["services"][0]["resourceKind"] = "laser"
    for master in data["masters"]:
        master["locationId"] = location_id
    assert client.put("/api/admin/config", json=data).status_code == 200
    fresh = client.get("/api/admin/config").json()["data"]
    assert fresh["services"][0]["resourceKind"] == "laser"
    assert all(m["locationId"] == location_id for m in fresh["masters"])

    _, first = _book(client, tomorrow, master="alex")
    from backend.app import deps
    from backend.app.db import BookingResource
    from sqlalchemy import select
    with deps.runtime.store.session_factory() as session:
        assert len(list(session.scalars(select(BookingResource)).all())) == 1
    taylor_slots = client.get("/api/slots", params={
        "masterId": "taylor", "serviceId": "haircut", "date": tomorrow,
    }).json()["slots"]
    same = next(x for x in taylor_slots if x["time"] == first["time"])
    second = client.post("/api/book", json={
        "masterId": "taylor", "serviceId": "haircut", "date": tomorrow,
        "time": same["time"], "name": "Мария", "phone": "+598 99999999", "token": same["token"],
    })
    assert second.status_code == 409
    assert "ресурс" in second.json()["detail"]


def test_public_booking_page(client):
    page = client.get("/book/demo-salon")
    assert page.status_code == 200
    assert "widget.js" in page.text


def test_structured_onboarding_creates_ready_business(client):
    response = client.post("/api/admin/onboarding", json={
        "slug": "new-studio", "title": "New Studio", "copyFrom": "demo-salon",
        "salon": {"name": "New Studio", "address": "Centro, Montevideo"},
    })
    assert response.status_code == 200, response.text
    assert response.json()["publicBookingPath"] == "/book/new-studio"
    assert client.get("/api/config", params={"tenant": "new-studio"}).json()["salon"]["name"] == "New Studio"
