"""Проверки, ради которых инструменты и существуют: без них модель могла бы навредить."""

from __future__ import annotations

import pytest

from backend.app.policies import slot_token
from backend.app.tools import ToolContext, ToolError


def first_slot(tools, tomorrow, service_id="haircut", master_id="alex"):
    data = tools.get_free_slots(service_id=service_id, master_id=master_id, date_from=tomorrow, days=1)
    day = data["availability"][0]["days"][0]
    return day["slots"][0]


def book(tools, slot, ctx, *, name="Jordan", phone="+598 91234567", service="haircut", master="alex"):
    return tools.create_booking(
        service_id=service, master_id=master, start=slot["start"], customer_name=name,
        phone=phone, confirmation_token=slot["token"], ctx=ctx,
    )


def test_slots_respect_service_duration(tools, tomorrow):
    """Окрашивание 150 мин: последний слот должен заканчиваться не позже 20:00."""
    data = tools.get_free_slots(service_id="color", master_id="alex", date_from=tomorrow, days=1)
    times = [s["time"] for s in data["availability"][0]["days"][0]["slots"]]
    assert times[0] == "11:00"
    assert all(t <= "17:30" for t in times), times


def test_master_shift_narrows_the_salon_hours(tools, tenant, tomorrow):
    """У мастера своя смена: салон открыт с 11:00, а он начинает в 14:00."""
    tenant.salon["masters"][0]["workHours"] = {"start": "14:00", "end": "17:00"}
    times = [s["time"] for s in first_day_slots(tools, tomorrow)]
    assert times[0] == "14:00"
    assert all(t <= "16:00" for t in times), times   # стрижка час, закрытие в 17:00


def test_empty_shift_means_the_salon_hours(tools, tenant, tomorrow):
    """Пусто — «как у салона», а не «не работает»."""
    tenant.salon["masters"][0]["workHours"] = {"start": "", "end": ""}
    assert first_day_slots(tools, tomorrow)[0]["time"] == "11:00"


def test_half_filled_shift_takes_the_rest_from_the_salon(tools, tenant, tomorrow):
    """Указан только конец смены — начало берём у салона."""
    tenant.salon["masters"][0]["workHours"] = {"start": "", "end": "13:00"}
    times = [s["time"] for s in first_day_slots(tools, tomorrow)]
    assert times[0] == "11:00" and times[-1] == "12:00"


def first_day_slots(tools, tomorrow, service_id="haircut", master_id="alex"):
    data = tools.get_free_slots(service_id=service_id, master_id=master_id, date_from=tomorrow, days=1)
    return data["availability"][0]["days"][0]["slots"]


def test_master_without_service_is_rejected(tools, tomorrow):
    with pytest.raises(ToolError, match="не делает|ни один"):
        tools.get_free_slots(service_id="color", master_id="taylor", date_from=tomorrow)


def test_booking_requires_explicit_confirmation(tools, tomorrow):
    slot = first_slot(tools, tomorrow)
    ctx = ToolContext(conversation_id="c1", history=[{"role": "user", "content": "а сколько стоит?"}])
    with pytest.raises(ToolError, match="не подтвердил"):
        book(tools, slot, ctx)


def test_decline_blocks_booking(tools, tomorrow):
    slot = first_slot(tools, tomorrow)
    ctx = ToolContext(conversation_id="c1", history=[{"role": "user", "content": "нет, не надо"}])
    with pytest.raises(ToolError, match="не подтвердил"):
        book(tools, slot, ctx)


def test_invented_time_is_rejected(tools, tomorrow, confirmed_ctx):
    """Время, которого клиенту не показывали, забронировать нельзя даже с подтверждением."""
    with pytest.raises(ToolError, match="не предлагалось"):
        tools.create_booking(
            service_id="haircut", master_id="alex", start=f"{tomorrow}T03:00:00-03:00",
            customer_name="Jordan", phone="+598 91234567",
            confirmation_token="поддельный-токен", ctx=confirmed_ctx,
        )


def test_token_is_bound_to_master_and_time(tools, tomorrow, confirmed_ctx):
    slot = first_slot(tools, tomorrow)
    with pytest.raises(ToolError, match="не предлагалось"):
        tools.create_booking(  # токен Alex не годится для Нины
            service_id="haircut", master_id="taylor", start=slot["start"],
            customer_name="Jordan", phone="+598 91234567",
            confirmation_token=slot["token"], ctx=confirmed_ctx,
        )


def test_double_booking_is_blocked(tools, tomorrow, confirmed_ctx):
    slot = first_slot(tools, tomorrow)
    book(tools, slot, confirmed_ctx)
    with pytest.raises(ToolError) as exc:
        book(tools, slot, confirmed_ctx, name="Другой", phone="+598 99999999")
    assert exc.value.conflict


def test_slot_disappears_after_booking(tools, tomorrow, confirmed_ctx):
    slot = first_slot(tools, tomorrow)
    book(tools, slot, confirmed_ctx)
    data = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow, days=1)
    times = [s["time"] for s in data["availability"][0]["days"][0]["slots"]]
    assert slot["time"] not in times


def test_idempotency_returns_same_booking(tools, tomorrow, confirmed_ctx):
    """Повторный вызов с теми же параметрами не создаёт вторую запись."""
    slot = first_slot(tools, tomorrow)
    first = book(tools, slot, confirmed_ctx)
    again = book(tools, slot, confirmed_ctx)
    assert first["booking_id"] == again["booking_id"]


def test_daily_limit_per_phone(tools, tomorrow, confirmed_ctx):
    data = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow, days=1)
    # Стрижка 60 мин при шаге 30 — берём каждый второй слот, чтобы они не пересекались.
    slots = data["availability"][0]["days"][0]["slots"][::2]
    for slot in slots[:3]:
        book(tools, slot, confirmed_ctx)
    with pytest.raises(ToolError, match="максимум записей"):
        book(tools, slots[3], confirmed_ctx)


def test_bad_phone_rejected(tools, tomorrow, confirmed_ctx):
    slot = first_slot(tools, tomorrow)
    with pytest.raises(ToolError, match="телефон"):
        book(tools, slot, confirmed_ctx, phone="123")


def test_cancel_requires_confirmation_and_works(tools, tomorrow, confirmed_ctx):
    slot = first_slot(tools, tomorrow)
    created = book(tools, slot, confirmed_ctx)

    unconfirmed = ToolContext(conversation_id="c1", history=[{"role": "user", "content": "хочу перенести"}])
    with pytest.raises(ToolError, match="не подтвердил"):
        tools.cancel_booking(booking_id=created["booking_id"], ctx=unconfirmed)

    result = tools.cancel_booking(booking_id=created["booking_id"], ctx=confirmed_ctx)
    assert result["cancelled"] is True

    data = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow, days=1)
    times = [s["time"] for s in data["availability"][0]["days"][0]["slots"]]
    assert slot["time"] in times  # слот снова свободен


def test_cancel_disabled_escalates(tools, tomorrow, confirmed_ctx):
    tools.settings.integration["policies"]["allowCancel"] = False
    with pytest.raises(ToolError, match="отключена"):
        tools.cancel_booking(booking_id="whatever", ctx=confirmed_ctx)


def test_handoff_returns_admin_contact(tools, confirmed_ctx):
    result = tools.handoff_to_human(reason="Жалоба на качество", ctx=confirmed_ctx)
    assert result["handed_off"] is True
    assert result["contact"] == "+598 99000101"


def test_calendar_failure_rolls_back_booking(tools, tomorrow, confirmed_ctx, monkeypatch):
    """Если календарь отказал — записи не остаётся, и клиенту не говорят «вы записаны»."""
    from backend.app.calendar_service import CalendarError

    slot = first_slot(tools, tomorrow)

    def boom(**kwargs):
        raise CalendarError("500 from Google")

    monkeypatch.setattr(tools.calendar, "create_event", boom)
    with pytest.raises(ToolError, match="не принял запись"):
        book(tools, slot, confirmed_ctx)

    # Слот снова свободен — «висящей» записи не осталось.
    data = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow, days=1)
    times = [s["time"] for s in data["availability"][0]["days"][0]["slots"]]
    assert slot["time"] in times


def test_evening_slots_reach_the_model(tools, tenant, tomorrow):
    """Вечерние окна не должны теряться в выдаче инструмента.

    Список обрезался двенадцатью окнами: при шаге 30 минут они кончались на
    16:30, и на просьбу «хочу в 17:00» модель отвечала, что такого времени нет,
    хотя салон работает до 20:00.
    """
    result = tools.get_free_slots(service_id="haircut", master_id="alex",
                                  date_from=tomorrow, days=1)
    day = result["availability"][0]["days"][0]
    times = [s["time"] for s in day["slots"]]

    hours = tenant.salon["workHours"]
    assert times[0] >= hours["start"], times
    # Либо день влез целиком — тогда видно вечер, либо выдача честно помечена.
    assert times[-1] >= "17:00" or day.get("truncated") is True, (times, day.get("truncated"))


# --- пересечение записей ------------------------------------------------------

def test_long_service_blocks_the_time_inside_it(tools, tenant, tomorrow, confirmed_ctx):
    """Окрашивание на 150 минут занимает все 150, а не только своё начало.

    Проверка идёт при выключенной перепроверке слота: уникальный индекс ловит
    лишь совпадение начала, и без отдельной проверки пересечения стрижка на
    середине окрашивания создалась бы поверх него.
    """
    color = first_slot(tools, tomorrow, service_id="color")
    book(tools, color, confirmed_ctx, service="color")

    tenant.integration["policies"]["recheckSlotBeforeInsert"] = False
    inside = color["start"].replace("T11:00", "T12:00")
    with pytest.raises(ToolError) as exc:
        tools.create_booking(
            service_id="haircut", master_id="alex", start=inside, customer_name="Другой",
            phone="+598 99999999",
            confirmation_token=slot_token("alex", "haircut", inside, tenant.slug),
            ctx=confirmed_ctx,
        )
    assert exc.value.conflict
    assert "пересекается" in exc.value.message


def test_slots_skip_the_whole_length_of_a_booking(tools, tomorrow, confirmed_ctx):
    """После окрашивания в 11:00 свободные окна начинаются не раньше 13:30."""
    color = first_slot(tools, tomorrow, service_id="color")
    book(tools, color, confirmed_ctx, service="color")
    times = [s["time"] for s in first_day_slots(tools, tomorrow)]
    assert all(t >= "13:30" for t in times), times


def test_visit_marked_completed_still_holds_the_time(tools, tenant, store, tomorrow, confirmed_ctx):
    """«Пришёл» мастер отмечает в начале визита — время остаётся занятым."""
    color = first_slot(tools, tomorrow, service_id="color")
    booking = book(tools, color, confirmed_ctx, service="color")
    store.set_booking_status(booking["booking_id"], "completed", tenant_id=tenant.slug)
    times = [s["time"] for s in first_day_slots(tools, tomorrow)]
    assert all(t >= "13:30" for t in times), times


# --- запас времени до визита --------------------------------------------------

def test_lead_time_hides_the_nearest_hours(tools, tenant, tomorrow):
    """Ближайшие часы клиенту не предлагаются.

    Запас берём с запасом в сутки с лишним: проверка «ближайшие два часа»
    зависела бы от того, когда её запустили, и после восьми вечера падала
    сама по себе — сегодняшних окон к тому времени просто не остаётся.
    """
    from datetime import timedelta

    from backend.app.slots import free_slots
    from backend.app.timeutil import now

    tenant.salon["leadTimeMinutes"] = 26 * 60
    edge = now(tenant.timezone) + timedelta(minutes=26 * 60)
    slots = free_slots(tenant, tools.calendar, tenant.masters[0], tenant.service("haircut"), tomorrow)
    assert all(s["start"] >= edge for s in slots), [s["time"] for s in slots[:3]]

    # Без запаса тот же день полон окон — значит отсекает именно он.
    tenant.salon["leadTimeMinutes"] = 0
    assert free_slots(tenant, tools.calendar, tenant.masters[0], tenant.service("haircut"), tomorrow)


def test_booking_sooner_than_lead_time_is_refused(tools, tenant, confirmed_ctx):
    """Подпись слота не стареет — запас времени проверяется при самой записи."""
    from datetime import timedelta

    from backend.app.timeutil import now

    tenant.salon["leadTimeMinutes"] = 120
    soon = (now(tenant.timezone) + timedelta(minutes=30)).replace(second=0, microsecond=0).isoformat()
    with pytest.raises(ToolError, match="не раньше"):
        tools.create_booking(
            service_id="haircut", master_id="alex", start=soon, customer_name="Jordan",
            phone="+598 91234567",
            confirmation_token=slot_token("alex", "haircut", soon, tenant.slug),
            ctx=confirmed_ctx,
        )


# --- календарь смен -----------------------------------------------------------

def test_day_off_shift_removes_the_day(tools, tenant, tomorrow):
    """Выходной на дату закрывает день, даже если по сетке мастер работает."""
    from backend.app.slots import available_days

    from backend.app.slots import free_slots

    tenant.salon["masters"][0]["shifts"] = {tomorrow: {"off": True}}
    days = [d["date"] for d in available_days(tenant, tenant.masters[0])]
    assert tomorrow not in days
    # Именно этот день, а не «ближайший доступный»: обзор окон уехал бы на 22-е.
    assert not free_slots(tenant, tools.calendar, tenant.masters[0],
                          tenant.service("haircut"), tomorrow)


def test_shift_opens_a_day_outside_the_week_grid(tools, tenant, tomorrow):
    """Правка на дату сильнее недельной сетки в обе стороны."""
    from backend.app.slots import available_days

    tenant.salon["masters"][0]["workDays"] = []
    tenant.salon["masters"][0]["shifts"] = {tomorrow: {"start": "12:00", "end": "14:00"}}
    assert tomorrow in [d["date"] for d in available_days(tenant, tenant.masters[0])]
    times = [s["time"] for s in first_day_slots(tools, tomorrow)]
    assert times == ["12:00", "12:30", "13:00"]


@pytest.mark.parametrize("phone", ["+5491123456789", "+34612345678", "+79161234567"])
def test_foreign_phone_with_country_code_is_accepted(phone):
    """Записаться можно с номера любой страны — был бы код страны."""
    from backend.app.policies import needs_country_code, valid_phone

    assert not needs_country_code(phone, "598")
    assert valid_phone(phone, "598")


@pytest.mark.parametrize("phone", ["099000102", "99000102"])
def test_local_phone_still_works_without_code(phone):
    """Уругваец по-прежнему набирает номер так, как набирает его дома."""
    from backend.app.policies import needs_country_code, valid_phone

    assert not needs_country_code(phone, "598")
    assert valid_phone(phone, "598")


def test_foreign_phone_without_code_is_rejected():
    """«11 2345 6789» без плюса — аргентинский номер, а не уругвайский.

    Пока подстановка кода была безусловной, запись создавалась, а
    подтверждение уходило чужому человеку в Уругвае.
    """
    from backend.app.policies import needs_country_code, valid_phone

    assert needs_country_code("1123456789", "598")
    assert not valid_phone("1123456789", "598")


def test_repeated_digits_are_not_a_phone():
    """«1111111111» проходило проверку «хотя бы семь цифр» — и молчало."""
    from backend.app.policies import valid_phone

    assert not valid_phone("1111111111", "598")


def test_short_number_is_incomplete_not_foreign():
    """Семь цифр — неполный номер, а не «номер другой страны».

    Клиенту отвечали «укажите код страны», и он шёл искать ошибку там, где её
    нет: цифр не хватает, кодом это не лечится.
    """
    from backend.app.policies import phone_problem

    assert phone_problem("4786877", "598") == "bad_phone"
    assert phone_problem("99000102", "598") == ""


def test_american_number_needs_its_plus():
    """Американка набирает домашние десять цифр — без «+1» это чужой номер."""
    from backend.app.policies import phone_problem

    assert phone_problem("3055550134", "598") == "need_country_code"
    assert phone_problem("+1 305 555 0134", "598") == ""


def test_american_client_books_with_country_code(tools, tenant, tomorrow, confirmed_ctx):
    """Запись с американского номера доходит до конца, а не до отказа.

    Живой случай: клиентка из США дошла до сводки и получила «номер другой
    страны» — с этого экрана поправить телефон было уже нечем.
    """
    slot = first_slot(tools, tomorrow)
    booking = book(tools, slot, confirmed_ctx, name="Sarah", phone="+1 305 555 0134")
    assert booking["booking_id"]


# --- групповые сессии ---------------------------------------------------------

def test_group_session_sells_every_seat(tools, tenant, tomorrow, confirmed_ctx):
    """Курс на несколько мест продаётся нескольким клиентам, а не одному.

    Услуга с `groupCapacity` больше единицы занимает время мастера целиком, но
    вмещает нескольких: до этой правки второй клиент получал «время
    пересекается», а окно вовсе исчезало из сетки после первой записи.
    """
    tenant.salon["services"][0]["groupCapacity"] = 3
    slot = first_slot(tools, tomorrow)

    book(tools, slot, confirmed_ctx, name="Первый", phone="+598 91111111")
    # Окно осталось в сетке: места ещё есть.
    assert slot["time"] in [s["time"] for s in first_day_slots(tools, tomorrow)]

    book(tools, slot, confirmed_ctx, name="Второй", phone="+598 92222222")
    book(tools, slot, confirmed_ctx, name="Третий", phone="+598 93333333")

    # Мест больше нет — окно уходит из сетки, а четвёртому отказывают по-человечески.
    assert slot["time"] not in [s["time"] for s in first_day_slots(tools, tomorrow)]
    with pytest.raises(ToolError, match="мест"):
        book(tools, slot, confirmed_ctx, name="Четвёртый", phone="+598 94444444")


def test_group_seats_are_counted_not_bookings(tools, tenant, tomorrow, confirmed_ctx):
    """Клиент, забравший два места из трёх, оставляет ровно одно."""
    tenant.salon["services"][0]["groupCapacity"] = 3
    slot = first_slot(tools, tomorrow)

    tools.create_booking(
        service_id="haircut", master_id="alex", start=slot["start"], customer_name="Пара",
        phone="+598 91111111", confirmation_token=slot["token"], group_size=2, ctx=confirmed_ctx)

    with pytest.raises(ToolError, match="осталось мест: 1"):
        tools.create_booking(
            service_id="haircut", master_id="alex", start=slot["start"], customer_name="Трое",
            phone="+598 92222222", confirmation_token=slot["token"], group_size=2,
            ctx=confirmed_ctx)

    book(tools, slot, confirmed_ctx, name="Один", phone="+598 92222222")


def test_ordinary_service_still_takes_the_slot_alone(tools, tomorrow, confirmed_ctx):
    """Обычная услуга осталась исключительной: общая сессия её правил не ослабила."""
    slot = first_slot(tools, tomorrow)
    book(tools, slot, confirmed_ctx)
    with pytest.raises(ToolError) as exc:
        book(tools, slot, confirmed_ctx, name="Другой", phone="+598 99999999")
    assert exc.value.conflict


def test_same_client_can_return_to_a_cancelled_slot(tools, tomorrow, confirmed_ctx):
    """Отменённая запись держала ключ идемпотентности — и слот «занят» навсегда.

    Мастер отменяет визит, клиент тем же вечером просит то же время обратно.
    Окно свободно, сетка его показывает, а вставка падала на уникальном
    `idempotency_key` прежней записи — и клиент получал «это время только что
    заняли». На проде так не записались трое подряд.
    """
    slot = first_slot(tools, tomorrow)
    first = book(tools, slot, confirmed_ctx)
    tools.cancel_booking(booking_id=first["booking_id"], ctx=confirmed_ctx)

    again = book(tools, slot, confirmed_ctx)
    assert again["booking_id"] != first["booking_id"]
    assert (again["date"], again["time"]) == (first["date"], first["time"])


def test_repeat_confirmation_still_returns_one_booking(tools, tomorrow, confirmed_ctx):
    """Версионирование ключа не должно превращать двойной клик в две записи."""
    slot = first_slot(tools, tomorrow)
    first = book(tools, slot, confirmed_ctx)
    tools.cancel_booking(booking_id=first["booking_id"], ctx=confirmed_ctx)
    second = book(tools, slot, confirmed_ctx)
    assert book(tools, slot, confirmed_ctx)["booking_id"] == second["booking_id"]


# --- время вне сетки меню --------------------------------------------------

def _coarse_grid(tenant):
    """Как у салона на проде: окна в меню раз в два часа."""
    tenant.salon["slotStepMinutes"] = 120
    return tenant


def test_free_time_between_menu_slots_is_bookable(tools, tenant, tomorrow, confirmed_ctx):
    """Запись в 15:00 на час, меню предлагает дальше 17:00 — но 16:00 свободно."""
    _coarse_grid(tenant)
    grid = [s["time"] for s in first_day_slots(tools, tomorrow)]
    assert grid == ["11:00", "13:00", "15:00", "17:00", "19:00"]
    at_15 = next(s for s in first_day_slots(tools, tomorrow) if s["time"] == "15:00")
    book(tools, at_15, confirmed_ctx)

    data = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow,
                                time="16:00")
    requested = data["availability"][0]["days"][0]["requested"]
    assert requested["free"] is True
    booking = book(tools, requested, confirmed_ctx, name="Другой", phone="+598 99887766")
    assert booking["time"] == "16:00"


def test_taken_time_comes_with_nearest_alternatives(tools, tenant, tomorrow, confirmed_ctx):
    _coarse_grid(tenant)
    at_15 = next(s for s in first_day_slots(tools, tomorrow) if s["time"] == "15:00")
    book(tools, at_15, confirmed_ctx)

    data = tools.get_free_slots(service_id="haircut", master_id="alex", date_from=tomorrow,
                                time="15:30")
    requested = data["availability"][0]["days"][0]["requested"]
    assert requested["free"] is False
    times = [s["time"] for s in requested["nearest"]]
    # Ближайшие с обеих сторон занятого часа: закончить к 15:00 или начать с 16:00.
    assert "14:00" in times and "16:00" in times, times
    assert all(len(s["token"]) == 32 for s in requested["nearest"])


def test_off_grid_time_still_respects_overlap(tools, tenant, tomorrow, confirmed_ctx):
    """Вне сетки — не значит без проверок: 14:30 на час наезжает на запись в 15:00."""
    from backend.app.slots import slot_at

    _coarse_grid(tenant)
    at_15 = next(s for s in first_day_slots(tools, tomorrow) if s["time"] == "15:00")
    book(tools, at_15, confirmed_ctx)
    master, service = tenant.masters[0], tenant.service("haircut")
    assert slot_at(tenant, tools.calendar, master, service, tomorrow, "14:30") is None
    assert slot_at(tenant, tools.calendar, master, service, tomorrow, "14:00")
    assert slot_at(tenant, tools.calendar, master, service, tomorrow, "19:30") is None  # после закрытия
    assert slot_at(tenant, tools.calendar, master, service, tomorrow, "16:07") is None  # опечатка
