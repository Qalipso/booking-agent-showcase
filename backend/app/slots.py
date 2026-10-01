"""Расчёт свободных окон: график салона, график мастера, длительность услуги, занятость."""

from __future__ import annotations

from datetime import timedelta

from .calendar_service import CalendarService
from .tenants import Tenant
from .timeutil import (
    TODAY_LABEL, human_date, minutes_of, norm_lang, now, time_str, today_key, weekday_of, zoned,
)


def shift_of(master: dict, date_str: str) -> dict:
    """Персональная правка графика на конкретный день, если мастер её поставил.

    Пустой словарь означает «особой правки нет» — работает недельная сетка.
    Формат: ``{"off": true}`` — не работает; ``{"start": "12:00", "end": "16:00"}``
    — работает в свои часы; ``{}`` в календаре не хранится вовсе.
    """
    if not date_str:
        return {}
    shift = (master.get("shifts") or {}).get(date_str)
    return dict(shift) if isinstance(shift, dict) else {}


def working_day(settings: Tenant, master: dict, date_str: str) -> bool:
    """Работает ли мастер в этот день.

    Правка на дату сильнее недельной сетки в обе стороны: мастер может закрыть
    рабочий вторник и открыть выходное воскресенье, не переписывая расписание
    целиком. Именно это и нужно от календаря смен.
    """
    shift = shift_of(master, date_str)
    if shift:
        return not shift.get("off")
    days = master.get("workDays") or settings.salon.get("workDays") or []
    return weekday_of(date_str) in [int(d) for d in days]


def work_hours(settings: Tenant, master: dict, date_str: str = "") -> dict:
    """Часы на день: правка на дату, иначе часы мастера, иначе часы салона.

    Пустое поле — «как у салона», а не «не работает»: у большинства мастеров
    график совпадает с салоном, и заставлять владельца дублировать его в каждой
    карточке значит гарантированно получить расхождение при смене часов салона.
    Половинчатая настройка тоже осмысленна: указан только конец — начало берётся
    у салона.
    """
    salon = settings.salon.get("workHours") or {}
    own = master.get("workHours") or {}
    shift = shift_of(master, date_str)
    start = ((shift.get("start") or "").strip() or (own.get("start") or "").strip()
             or salon.get("start"))
    end = ((shift.get("end") or "").strip() or (own.get("end") or "").strip()
           or salon.get("end"))
    return {"start": start, "end": end}


def lead_minutes(settings: Tenant) -> int:
    """Насколько заранее клиент может занять ближайшее окно."""
    return int(settings.salon.get("leadTimeMinutes", 120))


# Шаг, которым ищем соседние свободные окна, когда названное время занято.
# Сетка меню бывает крупной (у салона — два часа), а ближайший вариант к
# «хочу в 15:00» нередко «14:15» или «15:45»: запись закончилась раньше.
NEARBY_STEP = 15
# Варианты не должны дублировать друг друга: «13:45 или 14:00» — это один
# вариант, а не два.
NEARBY_SPREAD = 30


def _day_frame(settings: Tenant, calendar: CalendarService, master: dict, service: dict,
               date_str: str, exclude_booking_id: str = "") -> dict | None:
    """Всё, что нужно для проверки окон дня: часы, занятость, запас времени.

    ``None`` — мастер в этот день не работает или не делает эту услугу.
    """
    if not working_day(settings, master, date_str):
        return None
    if service["id"] not in (master.get("services") or []):
        return None
    tz_name = settings.timezone
    hours = work_hours(settings, master, date_str)
    day_start = zoned(date_str, hours["start"], tz_name)
    day_end = zoned(date_str, hours["end"], tz_name)
    return {
        "open": minutes_of(hours["start"]),
        "close": minutes_of(hours["end"]),
        "busy": calendar.busy(master, day_start, day_end, exclude_booking_id=exclude_booking_id),
        "duration": int(service["duration"]),
        "not_before": now(tz_name) + timedelta(minutes=lead_minutes(settings)),
        # Услуга с несколькими местами — общая сессия: она занимает время мастера
        # целиком, но остаётся свободной, пока в ней есть места. Без этого курс на
        # десять человек исчезал из сетки после первой же записи.
        "capacity": max(1, int(service.get("groupCapacity") or 1)),
    }


def _slot_at_minute(settings: Tenant, calendar: CalendarService, master: dict, service: dict,
                    date_str: str, frame: dict, minute: int) -> dict | None:
    """Окно, начинающееся в эту минуту дня, если оно целиком свободно."""
    if minute < frame["open"] or minute + frame["duration"] > frame["close"]:
        return None
    start = zoned(date_str, time_str(minute), settings.timezone)
    end = start + timedelta(minutes=frame["duration"])
    if start < frame["not_before"]:
        return None
    # Пересечение проверяем по всему интервалу услуги, а не по её началу:
    # окрашивание на три часа занимает три часа, и записать поверх него
    # стрижку через полчаса нельзя.
    overlap = [span for span in frame["busy"] if start < span[1] and end > span[0]]
    if overlap and not _own_session(settings, calendar, master, service, start, end,
                                    overlap, frame["capacity"]):
        return None
    return {"time": time_str(minute), "start": start, "end": end}


def free_slots(settings: Tenant, calendar: CalendarService, master: dict, service: dict,
               date_str: str, exclude_booking_id: str = "", step: int | None = None) -> list[dict]:
    """Свободные окна мастера на день.

    ``exclude_booking_id`` нужен переносу: время самой переносимой записи
    остаётся в списке — иначе панель прячет окно, в котором клиент стоит
    сейчас, и «перенести на полчаса позже» приходится делать вслепую.
    ``step`` — шаг поиска вместо шага меню салона.
    """
    frame = _day_frame(settings, calendar, master, service, date_str, exclude_booking_id)
    if frame is None:
        return []
    step = max(1, int(step or settings.salon.get("slotStepMinutes", 30)))
    slots = []
    for minute in range(frame["open"], frame["close"] - frame["duration"] + 1, step):
        slot = _slot_at_minute(settings, calendar, master, service, date_str, frame, minute)
        if slot:
            slots.append(slot)
    return slots


def slot_at(settings: Tenant, calendar: CalendarService, master: dict, service: dict,
            date_str: str, time: str, exclude_booking_id: str = "") -> dict | None:
    """Свободно ли конкретное время, даже если его нет в сетке меню.

    Сетка — это то, что клиенту удобно показать кнопками, а не то, когда
    мастер свободен. Запись в 15:00 на 45 минут при шаге два часа прячет
    16:00 из меню, хотя мастер в это время ничем не занят, — и клиент,
    написавший «хочу в 16», должен туда записаться.
    """
    try:
        minute = minutes_of(time)
    except ValueError:
        return None
    # Время вроде 16:07 — опечатка, а не пожелание: принимаем кратное пяти минутам.
    if minute % 5:
        return None
    frame = _day_frame(settings, calendar, master, service, date_str, exclude_booking_id)
    if frame is None:
        return None
    return _slot_at_minute(settings, calendar, master, service, date_str, frame, minute)


def nearby_slots(settings: Tenant, calendar: CalendarService, master: dict, service: dict,
                 date_str: str, time: str, limit: int = 3) -> list[dict]:
    """Ближайшие к названному времени свободные окна того же дня — по времени.

    Берём и до, и после: «в 15 занято» полезнее всего закрыть вариантами
    «14:15 или 15:45», а не списком всего дня. Если с одной стороны окон нет,
    добираем с другой.
    """
    try:
        wanted = minutes_of(time)
    except ValueError:
        return []
    step = min(NEARBY_STEP, int(settings.salon.get("slotStepMinutes", 30)) or NEARBY_STEP)
    found = [s for s in free_slots(settings, calendar, master, service, date_str, step=step)
             if s["time"] != time]
    before = sorted((s for s in found if minutes_of(s["time"]) < wanted),
                    key=lambda s: wanted - minutes_of(s["time"]))
    after = sorted((s for s in found if minutes_of(s["time"]) > wanted),
                   key=lambda s: minutes_of(s["time"]) - wanted)
    picked: list[dict] = []

    def spread(side: list[dict]) -> None:
        while side and any(abs(minutes_of(side[0]["time"]) - minutes_of(p["time"])) < NEARBY_SPREAD
                           for p in picked):
            side.pop(0)

    while len(picked) < limit:
        spread(before)
        spread(after)
        if not (before or after):
            break
        # Чередуем стороны, начиная с ближайшей.
        sides = sorted([x for x in (before, after) if x],
                       key=lambda side: abs(minutes_of(side[0]["time"]) - wanted))
        for side in sides:
            if len(picked) < limit:
                picked.append(side.pop(0))
                spread(before)
                spread(after)
    return sorted(picked, key=lambda s: s["time"])


def _own_session(settings: Tenant, calendar: CalendarService, master: dict, service: dict,
                 start, end, overlap: list, capacity: int) -> bool:
    """Занято ли окно «своей же» сессией, в которой ещё есть места.

    Для общей сессии единственное, что имеет право стоять в это время, — она
    сама: событие ровно на те же начало и конец. Всё остальное (другая услуга,
    личная встреча мастера в Google-календаре) окно по-прежнему закрывает.
    """
    if capacity <= 1:
        return False
    if any(span != (start, end) for span in overlap):
        return False
    store = getattr(calendar, "store", None)
    if store is None:
        return False
    taken = store.session_seats(master["id"], service["id"], start, tenant_id=settings.slug)
    return taken < capacity


def available_days(settings: Tenant, master: dict, limit: int = 8, lang: str = "ru") -> list[dict]:
    horizon = int(settings.salon.get("bookingHorizonDays", 14))
    tz_name = settings.timezone
    today = today_key(tz_name)
    from .timeutil import date_keys

    out = []
    for date_str in date_keys(tz_name, horizon):
        if not working_day(settings, master, date_str):
            continue
        label = TODAY_LABEL[norm_lang(lang)] if date_str == today else human_date(date_str, lang)
        out.append({"date": date_str, "label": label})
        if len(out) >= limit:
            break
    return out
