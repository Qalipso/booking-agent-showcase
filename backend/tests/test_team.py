"""Кабинет мастера: вход по личной ссылке, свой день, свой график.

Главное здесь — не «работает ли экран», а границы: мастер не должен видеть
чужие записи и трогать чужой график, а отозванная ссылка обязана закрывать уже
открытый кабинет, а не «следующий вход».
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def cabinet(monkeypatch):
    """Тестовый клиент ходит по http, а Secure-cookie по http не сохраняется —
    кабинет не открывался бы вовсе. Заодно обнуляем счётчик попыток: он общий
    на процесс, и десятого теста хватило бы, чтобы получить 429 на ровном месте."""
    from backend.app.routers import team

    monkeypatch.setenv("ADMIN_COOKIE_INSECURE", "1")
    team._attempts._hits.clear()  # noqa: SLF001


PIN = "8461"   # ПИН, который мастер придумывает сам при первом входе


def issue(client, master_id: str = "alex") -> str:
    """Владелец выдаёт мастеру ссылку из панели — как на самом деле."""
    res = client.post(f"/api/admin/masters/{master_id}/access")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "pin" not in body, "ПИН придумывает мастер, владельцу его знать неоткуда"
    return body["link"].split("#k=", 1)[1]


def enter(client, master_id: str = "alex", pin: str = PIN) -> str:
    """Ссылка плюс первый вход, на котором мастер задаёт себе ПИН."""
    key = issue(client, master_id)
    res = client.post("/api/team/enter", json={"key": key, "pin": pin})
    assert res.status_code == 200, res.text
    return key


def book(client, day: str, master_id: str = "alex", name: str = "Мария") -> dict:
    slots = client.get("/api/slots", params={"masterId": master_id, "serviceId": "haircut",
                                             "date": day}).json()["slots"]
    res = client.post("/api/admin/bookings", json={
        "masterId": master_id, "serviceId": "haircut", "date": day,
        "time": slots[0]["time"], "name": name, "phone": "+598 99123456",
    })
    assert res.status_code == 200, res.text
    return res.json()["booking"]


def test_master_sets_his_own_pin_on_the_first_visit(client):
    """Первый вход задаёт ПИН, дальше он же и спрашивается."""
    key = issue(client)

    # Экран сначала спрашивает, что показать: придумать ПИН или ввести.
    first = client.post("/api/team/start", json={"key": key}).json()
    assert first["stage"] == "setup"
    assert first["master"] == "Alex" and first["salon"]

    opened = client.post("/api/team/enter", json={"key": key, "pin": PIN})
    assert opened.status_code == 200, opened.text
    assert opened.json()["master"] == "Alex"

    # Со второго раза ссылка уже спрашивает придуманные цифры.
    assert client.post("/api/team/start", json={"key": key}).json()["stage"] == "pin"
    client.post("/api/team/logout")
    assert client.post("/api/team/enter", json={"key": key, "pin": "1357"}).status_code == 401
    assert client.post("/api/team/enter", json={"key": key, "pin": PIN}).status_code == 200


def test_pin_survives_the_owner_reissuing_the_link(client):
    """ПИН принадлежит мастеру, а не ссылке: перевыдача его не трогает."""
    key = enter(client)
    client.post("/api/team/logout")

    fresh = issue(client)   # владелец выдал новую ссылку
    assert client.post("/api/team/enter", json={"key": key, "pin": PIN}).status_code == 401
    # Новая ссылка — тот же мастер, и ПИН у него прежний.
    assert client.post("/api/team/start", json={"key": fresh}).json()["stage"] == "setup"


def test_a_made_up_pin_must_not_be_trivial(client):
    """«1234» подберут раньше, чем сработает счётчик попыток."""
    key = issue(client)
    weak = client.post("/api/team/enter", json={"key": key, "pin": "1234"})
    assert weak.status_code == 401
    assert "простой" in weak.json()["detail"]

    short = client.post("/api/team/enter", json={"key": key, "pin": "12"})
    assert short.status_code == 401
    assert "четыре цифры" in short.json()["detail"]

    assert client.post("/api/team/enter", json={"key": key, "pin": PIN}).status_code == 200


def test_owner_resets_a_forgotten_pin_without_a_new_link(client):
    """Забытый ПИН — мелочь: ссылка остаётся, мастер задаёт цифры заново."""
    key = enter(client)
    client.post("/api/team/logout")

    assert client.post("/api/admin/masters/alex/access/pin").json()["reset"] is True
    assert client.post("/api/team/start", json={"key": key}).json()["stage"] == "setup"
    # Старый ПИН больше ничего не значит — мастер придумывает новый.
    assert client.post("/api/team/enter", json={"key": key, "pin": "5309"}).status_code == 200
    assert client.post("/api/team/start", json={"key": key}).json()["stage"] == "pin"


def test_link_without_pin_opens_nothing(client):
    """Пересланная ссылка сама по себе бесполезна — в этом весь смысл ПИНа."""
    key = enter(client)
    client.post("/api/team/logout")
    assert client.post("/api/team/enter", json={"key": key}).status_code == 401
    assert client.post("/api/team/enter", json={"key": key, "pin": "0000"}).status_code == 401
    # Правильный ПИН после промахов всё ещё работает: промах не сжигает доступ.
    assert client.post("/api/team/enter", json={"key": key, "pin": PIN}).status_code == 200


def test_wrong_pin_says_how_many_tries_are_left(client):
    """Мастеру важно знать, что попытки кончаются, — иначе он не позвонит вовремя."""
    key = enter(client)
    res = client.post("/api/team/enter", json={"key": key, "pin": "9999"})
    assert res.status_code == 401
    assert "Осталось попыток: 4" in res.json()["detail"]


def test_pin_guessing_locks_the_cabinet(client):
    """Четыре цифры перебираются за вечер — после пяти промахов ключ молчит."""
    from backend.app import staff

    key = enter(client)
    for _ in range(staff.MAX_PIN_ATTEMPTS):
        client.post("/api/team/enter", json={"key": key, "pin": "0000"})

    blocked = client.post("/api/team/enter", json={"key": key, "pin": PIN})
    assert blocked.status_code == 429
    assert "попыток" in blocked.json()["detail"]

    # Панель показывает владельцу, что мастер сейчас не войдёт.
    row = next(m for m in client.get("/api/admin/masters/access").json()["masters"]
               if m["id"] == "alex")
    assert row["lockedUntil"]


def test_lockout_expires_and_the_master_gets_back(client):
    """Блокировка временная: мастер не должен ждать владельца до утра."""
    from datetime import timedelta

    from backend.app import staff
    from backend.app.db import MasterKey
    from backend.app.deps import runtime

    key = enter(client)
    for _ in range(staff.MAX_PIN_ATTEMPTS):
        client.post("/api/team/enter", json={"key": key, "pin": "0000"})
    assert client.post("/api/team/enter", json={"key": key, "pin": PIN}).status_code == 429

    # Отматываем срок блокировки назад — ждать четверть часа в тесте нечестно.
    with runtime.store.session_factory() as s:
        row = s.query(MasterKey).one()
        row.pin_locked_until = staff._now() - timedelta(minutes=1)  # noqa: SLF001
        s.commit()

    assert client.post("/api/team/enter", json={"key": key, "pin": PIN}).status_code == 200


def test_the_owner_never_learns_the_pin(client):
    """ПИН знает только мастер: в базе хеш, в панели — лишь факт, что он задан."""
    enter(client)
    listed = client.get("/api/admin/masters/access").json()["masters"]
    assert all("pin" not in m for m in listed)
    alex = next(m for m in listed if m["id"] == "alex")
    assert alex["pinSet"] is True

    sam = next(m for m in listed if m["id"] != "alex")
    assert sam["pinSet"] is False


def test_cabinet_is_closed_without_a_link(client):
    """Без ссылки кабинета нет: ни записей, ни графика."""
    assert client.get("/api/team/state").json() == {"authenticated": False}
    assert client.get("/api/team/agenda").status_code == 401
    assert client.get("/api/team/shifts").status_code == 401
    assert client.put("/api/team/shifts", json={"date": "2030-01-01", "mode": "off"}).status_code == 401


def test_made_up_key_does_not_open_anything(client):
    """Придуманный ключ — 401, и ни намёка, чем он не подошёл."""
    res = client.post("/api/team/enter", json={"key": "не-ключ", "pin": "8461"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Ссылка не подошла"
    assert client.post("/api/team/start", json={"key": "не-ключ"}).status_code == 401


def test_agenda_shows_only_own_bookings(client, tomorrow):
    """Мастер видит свой день. Чужие записи в его кабинет не попадают."""
    book(client, tomorrow, "alex", "Мария")
    book(client, tomorrow, "taylor", "Ольга")

    enter(client, "alex")
    day = client.get("/api/team/agenda", params={"span": "day", "date": tomorrow}).json()
    assert day["days"][0]["count"] == 1
    names = [b["client"] for b in day["days"][0]["bookings"]]
    assert names == ["Мария"]
    # Телефон нужен, чтобы позвонить опаздывающему, — он и есть смысл экрана.
    assert day["days"][0]["bookings"][0]["phone"]


def test_week_and_month_cover_whole_periods(client, tomorrow):
    """Неделя — семь дней, месяц — все его дни, включая пустые и выходные."""
    enter(client)
    week = client.get("/api/team/agenda", params={"span": "week", "date": tomorrow}).json()
    assert len(week["days"]) == 7
    assert week["days"][0]["date"] <= tomorrow <= week["days"][-1]["date"]

    month = client.get("/api/team/agenda", params={"span": "month", "date": tomorrow}).json()
    assert len(month["days"]) in (28, 29, 30, 31)
    assert all(d["date"].startswith(tomorrow[:7]) for d in month["days"])


def test_master_closes_his_own_day(client, tomorrow):
    """Выходной, поставленный мастером, закрывает окна для клиентов."""
    enter(client)
    res = client.put("/api/team/shifts", json={"date": tomorrow, "mode": "off"})
    assert res.status_code == 200, res.text
    day = next(d for d in res.json()["days"] if d["date"] == tomorrow)
    assert day["works"] is False

    free = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                            "date": tomorrow}).json()["slots"]
    assert free == []


def test_closing_a_busy_day_asks_first(client, tomorrow):
    """День с записями закрывается только осознанно: сначала отказ, потом force."""
    book(client, tomorrow)
    enter(client)
    res = client.put("/api/team/shifts", json={"date": tomorrow, "mode": "off"})
    assert res.status_code == 409
    assert res.json()["detail"]["bookings"] == 1

    forced = client.put("/api/team/shifts", json={"date": tomorrow, "mode": "off", "force": True})
    assert forced.status_code == 200


def test_master_cannot_touch_another_master(client, tomorrow):
    """Идентификатор мастера в запросах не принимается — только сессия.

    Иначе достаточно было бы подставить чужой, чтобы посмотреть чужой день
    и закрыть чужую смену.
    """
    enter(client, "alex")
    # Даже если приписать чужого мастера параметром, ответ остаётся своим.
    res = client.get("/api/team/agenda", params={"span": "day", "date": tomorrow,
                                                 "masterId": "taylor", "master": "taylor"}).json()
    assert res["master"] == "Alex"

    client.put("/api/team/shifts", json={"date": tomorrow, "mode": "off"})
    taylor = client.get("/api/admin/masters/taylor/shifts", params={"month": tomorrow[:7]}).json()
    assert next(d for d in taylor["days"] if d["date"] == tomorrow)["works"] is True


def test_revoked_link_closes_an_open_cabinet(client):
    """Отзыв — это «прямо сейчас», а не «в следующий раз»."""
    enter(client)
    assert client.get("/api/team/state").json()["authenticated"] is True

    assert client.delete("/api/admin/masters/alex/access").json()["revoked"] is True
    assert client.get("/api/team/state").json() == {"authenticated": False}
    assert client.get("/api/team/agenda").status_code == 401


def test_new_link_kills_the_old_one(client):
    """Вторая выдача гасит первую: две живые ссылки — это «отозвали одну из»."""
    first_key = enter(client)
    client.post("/api/team/logout")
    second_key = issue(client)
    assert client.post("/api/team/enter", json={"key": first_key, "pin": PIN}).status_code == 401
    assert client.post("/api/team/enter", json={"key": second_key, "pin": PIN}).status_code == 200


def test_owner_sees_who_has_access_but_never_the_key(client):
    """Панель показывает факт доступа и последний вход, но не ссылку и не ПИН."""
    before = client.get("/api/admin/masters/access").json()
    assert [m["issued"] for m in before["masters"]] == [False, False]

    enter(client, "alex")
    after = client.get("/api/admin/masters/access").json()
    alex = next(m for m in after["masters"] if m["id"] == "alex")
    assert alex["issued"] is True and alex["lastSeenAt"]
    assert not {"key", "link", "pin"} & set(alex)


def test_break_blocks_the_slot_and_can_be_removed(client, tomorrow):
    """Перерыв мастера занимает время так же, как запись."""
    enter(client)
    free_before = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                                   "date": tomorrow}).json()["slots"]
    at = free_before[0]["time"]
    end = f"{int(at[:2]) + 2:02d}:{at[3:]}"

    res = client.post("/api/team/breaks", json={"date": tomorrow, "start": at, "end": end,
                                                "title": "Обед"})
    assert res.status_code == 200, res.text

    free_after = client.get("/api/slots", params={"masterId": "alex", "serviceId": "haircut",
                                                  "date": tomorrow}).json()["slots"]
    assert at not in [s["time"] for s in free_after]

    block = client.get("/api/team/agenda", params={"span": "day", "date": tomorrow}) \
        .json()["days"][0]["blocks"][0]
    assert block["title"] == "Обед"
    assert client.delete(f"/api/team/breaks/{block['id']}").status_code == 200


def test_master_cannot_delete_a_foreign_break(client, tomorrow):
    """Чужой перерыв мастеру не принадлежит — 404, а не «убрано»."""
    made = client.post("/api/admin/time-blocks", json={
        "masterId": "taylor", "date": tomorrow, "start": "13:00", "end": "14:00", "title": "Обед"})
    assert made.status_code == 200, made.text
    block_id = made.json()["block"]["id"]

    enter(client, "alex")
    assert client.delete(f"/api/team/breaks/{block_id}").status_code == 404


def test_team_page_is_served_on_its_own_host(client):
    """Поддомен мастеров открывает кабинет в корне, рабочий домен — нет."""
    assert client.get("/team").status_code == 200
    assert "team.js" in client.get("/team").text
    assert client.get("/", headers={"host": "team.demo-salon.com"}).status_code == 200
    assert client.get("/", headers={"host": "bookings.demo-salon.com"}).status_code == 404


@pytest.mark.parametrize("path", ["/api/team/agenda", "/api/team/shifts"])
def test_deleted_master_loses_the_cabinet(client, tenants_dir, path):
    """Мастера убрали из салона — ссылка перестаёт открывать кабинет."""
    import json

    enter(client, "alex")
    salon_file = tenants_dir / "demo-salon" / "salon.json"
    salon = json.loads(salon_file.read_text(encoding="utf-8"))
    salon["masters"] = [m for m in salon["masters"] if m["id"] != "alex"]
    salon_file.write_text(json.dumps(salon, ensure_ascii=False), encoding="utf-8")

    from backend.app import deps
    from backend.app.tenants import registry

    registry._cache.clear()  # noqa: SLF001 — конфиг переписали снаружи, как на проде
    deps.runtime._by_tenant.clear()  # noqa: SLF001

    assert client.get(path).status_code == 401
