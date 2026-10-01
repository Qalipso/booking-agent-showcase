"""Оплата визита абонементом и сертификатом.

Способ оплаты `membership` и `certificate` принимался и раньше, но остаток
самого абонемента при этом не менялся: отметка и абонемент расходились с первой
же оплаты. Здесь проверяется, что списание есть, что оно ровно одно и что
выручка от него не удваивается.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _client(client, phone="+598 91234567", name="Jordan"):
    return client.post("/api/admin/clients", json={"name": name, "phone": phone}).json()["client"]


def _booking(client, tomorrow, *, phone="+598 91234567", price=1000):
    """Запись через ту же публичную дорогу, что и у виджета, — с ценой услуги."""
    data = client.get("/api/admin/config").json()["data"]
    data["services"][0]["priceAmount"] = price
    data["services"][0]["currency"] = "UYU"
    assert client.put("/api/admin/config", json=data).status_code == 200

    slot = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                            "date": tomorrow}).json()["slots"][0]
    booked = client.post("/api/book", json={
        "masterId": "alex", "serviceId": "haircut", "date": tomorrow, "time": slot["time"],
        "name": "Jordan", "phone": phone, "token": slot["token"],
    })
    assert booked.status_code == 200, booked.text
    return booked.json()["bookingId"]


def _asset(client, **fields):
    payload = {"kind": "membership", "code": "AB-1", "title": "Абонемент",
               "remainingUses": 2, "balanceAmount": 0, **fields}
    res = client.post("/api/admin/assets", json=payload)
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _assets(client):
    return {a["code"]: a for a in client.get("/api/admin/assets").json()["assets"]}


def _pay(client, booking_id, **body):
    return client.patch(f"/api/admin/bookings/{booking_id}/payment", json=body)


def test_membership_visit_is_debited(client, tomorrow):
    person = _client(client)
    booking_id = _booking(client, tomorrow)
    asset_id = _asset(client, clientId=person["id"])

    res = _pay(client, booking_id, paidAmount=0, paymentMethod="membership", assetId=asset_id)

    assert res.status_code == 200, res.text
    assert res.json()["method"] == "membership"
    assert _assets(client)["AB-1"]["uses"] == 1
    booking = next(b for b in client.get("/api/admin/bookings").json()["bookings"]
                   if b["id"] == booking_id)
    # Деньги пришли при продаже абонемента — в выручку визита они не идут второй раз.
    assert booking["paidAmount"] == 0


def test_second_request_does_not_debit_twice(client, tomorrow):
    person = _client(client)
    booking_id = _booking(client, tomorrow)
    asset_id = _asset(client, clientId=person["id"])

    _pay(client, booking_id, paidAmount=0, paymentMethod="membership", assetId=asset_id)
    again = _pay(client, booking_id, paidAmount=0, paymentMethod="membership", assetId=asset_id)

    assert again.status_code == 200
    assert _assets(client)["AB-1"]["uses"] == 1


def test_empty_membership_is_refused(client, tomorrow):
    person = _client(client)
    booking_id = _booking(client, tomorrow)
    asset_id = _asset(client, clientId=person["id"], remainingUses=0)

    res = _pay(client, booking_id, paidAmount=0, paymentMethod="membership", assetId=asset_id)

    assert res.status_code == 409
    assert "не осталось посещений" in res.json()["detail"]


def test_someone_elses_membership_is_refused(client, tomorrow):
    _client(client)
    other = _client(client, phone="+598 99887766", name="Мария")
    booking_id = _booking(client, tomorrow)
    asset_id = _asset(client, clientId=other["id"])

    res = _pay(client, booking_id, paidAmount=0, paymentMethod="membership", assetId=asset_id)

    assert res.status_code == 409
    assert "другому клиенту" in res.json()["detail"]


def test_certificate_covers_the_visit(client, tomorrow):
    person = _client(client)
    booking_id = _booking(client, tomorrow, price=900)
    asset_id = _asset(client, kind="certificate", code="CERT-1", title="Сертификат",
                      remainingUses=0, balanceAmount=1000, clientId=person["id"])

    res = _pay(client, booking_id, paidAmount=0, paymentMethod="certificate", assetId=asset_id)

    assert res.status_code == 200, res.text
    assert res.json()["method"] == "certificate"
    left = _assets(client)["CERT-1"]
    assert (left["balance"], left["status"]) == (100, "active")


def test_certificate_smaller_than_the_visit_is_refused(client, tomorrow):
    """Частичной оплаты нет: у записи один способ оплаты, и отказ объясняет числа."""
    person = _client(client)
    booking_id = _booking(client, tomorrow, price=1500)
    asset_id = _asset(client, kind="certificate", code="CERT-2", title="Сертификат",
                      remainingUses=0, balanceAmount=1000, clientId=person["id"])

    res = _pay(client, booking_id, paidAmount=0, paymentMethod="certificate", assetId=asset_id)

    assert res.status_code == 409
    assert "осталось 1000" in res.json()["detail"] and "1500" in res.json()["detail"]
    assert _assets(client)["CERT-2"]["balance"] == 1000


def test_spent_asset_changes_status(client, tomorrow):
    person = _client(client)
    booking_id = _booking(client, tomorrow)
    asset_id = _asset(client, clientId=person["id"], remainingUses=1)

    _pay(client, booking_id, paidAmount=0, paymentMethod="membership", assetId=asset_id)

    assert _assets(client)["AB-1"]["status"] == "spent"


def test_points_and_asset_are_not_mixed(client, tomorrow):
    person = _client(client)
    booking_id = _booking(client, tomorrow)
    asset_id = _asset(client, clientId=person["id"])

    res = _pay(client, booking_id, paidAmount=0, paymentMethod="membership",
               assetId=asset_id, loyaltyPoints=50)

    assert res.status_code == 409
    assert _assets(client)["AB-1"]["uses"] == 2


def test_expired_asset_is_refused(client, tomorrow):
    from backend.app import deps
    from backend.app.db import ClientAsset

    person = _client(client)
    booking_id = _booking(client, tomorrow)
    asset_id = _asset(client, clientId=person["id"])
    with deps.runtime.store.session_factory() as session:
        session.get(ClientAsset, asset_id).expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        session.commit()

    res = _pay(client, booking_id, paidAmount=0, paymentMethod="membership", assetId=asset_id)

    assert res.status_code == 409
    assert "истёк" in res.json()["detail"]


def test_asset_visit_shows_up_in_the_report_but_not_in_revenue(client, tomorrow):
    person = _client(client)
    booking_id = _booking(client, tomorrow, price=1000)
    asset_id = _asset(client, clientId=person["id"])
    _pay(client, booking_id, paidAmount=0, paymentMethod="membership", assetId=asset_id)
    client.post(f"/api/admin/bookings/{booking_id}/status", json={"status": "completed"})

    finance = client.get("/api/admin/finance").json()

    assert finance["revenue"] == 0
    assert finance["byAsset"] == 1000


def test_booking_row_names_the_asset(client, tomorrow):
    """Панель должна писать «оплачено абонементом AB-1, осталось 1», а не «0 UYU».

    Ноль без объяснения администратор читает как несохранённую оплату и жмёт
    «Оплата» ещё раз. Поэтому карточке нужны код актива и остаток по нему.
    """
    person = _client(client)
    booking_id = _booking(client, tomorrow)
    asset_id = _asset(client, clientId=person["id"])
    _pay(client, booking_id, paidAmount=0, paymentMethod="membership", assetId=asset_id)

    row = next(b for b in client.get("/api/admin/bookings").json()["bookings"]
               if b["id"] == booking_id)

    assert row["assetId"] == asset_id
    assert row["assetCode"] == "AB-1"
    assert row["assetKind"] == "membership"
    assert row["assetLeft"] == 1


def test_certificate_row_shows_money_left(client, tomorrow):
    """У сертификата остаток — деньги, и путать его с посещениями нельзя."""
    booking_id = _booking(client, tomorrow, price=300)
    asset_id = _asset(client, kind="certificate", code="CERT-1", title="Сертификат",
                      remainingUses=0, balanceAmount=1000)
    _pay(client, booking_id, paidAmount=0, paymentMethod="certificate", assetId=asset_id)

    row = next(b for b in client.get("/api/admin/bookings").json()["bookings"]
               if b["id"] == booking_id)

    assert row["assetKind"] == "certificate"
    assert row["assetLeft"] == 700


def test_booking_without_asset_has_no_asset_fields(client, tomorrow):
    booking_id = _booking(client, tomorrow)
    _pay(client, booking_id, paidAmount=1000, paymentMethod="cash")

    row = next(b for b in client.get("/api/admin/bookings").json()["bookings"]
               if b["id"] == booking_id)

    assert row["assetId"] is None
    assert row["assetCode"] is None
    assert row["assetLeft"] is None


def test_master_is_paid_for_a_membership_visit(client, tomorrow):
    """Абонемент не приносит денег в кассу, но работу мастера оплачивает.

    Комиссия считалась от `paidAmount`, а он у такого визита ноль — мастер
    оставался без процента за уже сделанную стрижку.
    """
    data = client.get("/api/admin/config").json()["data"]
    data["masters"][0]["commissionType"] = "percent"
    data["masters"][0]["commissionValue"] = 40
    assert client.put("/api/admin/config", json=data).status_code == 200

    person = _client(client)
    booking_id = _booking(client, tomorrow, price=1000)
    asset_id = _asset(client, clientId=person["id"])
    _pay(client, booking_id, paidAmount=0, paymentMethod="membership", assetId=asset_id)
    client.post(f"/api/admin/bookings/{booking_id}/status", json={"status": "completed"})

    finance = client.get("/api/admin/finance").json()

    assert finance["revenue"] == 0
    assert finance["payroll"]["alex"] == 400
