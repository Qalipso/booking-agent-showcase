"""График мастера: месяц смен и правка одного дня.

Одно и то же теперь делают два экрана — панель владельца и кабинет мастера.
Правила лежат здесь, а не в роутере: иначе мастер закрывал бы день в обход
проверок, которые владельцу мешают закрыть день с записями, и второй экран
неизбежно разошёлся бы с первым.

Недельная сетка в карточке мастера отвечает на вопрос «как обычно», календарь
смен — на вопрос «а в этот четверг». Второе меняется куда чаще первого, и
заставлять ради отпуска переписывать рабочие дни значит гарантированно получить
забытую галочку и запись в день, когда мастера нет в салоне.
"""

from __future__ import annotations

import logging
import re
from calendar import monthrange
from datetime import timedelta

from .deps import runtime
from .slots import shift_of, work_hours, working_day
from .tenants import TenantError
from .timeutil import TIME_PATTERN, parse_date, today_key, zoned

log = logging.getLogger("shifts")

MONTH_PATTERN = r"\d{4}-(0[1-9]|1[0-2])"


class ShiftError(RuntimeError):
    """Правку не приняли. ``status`` и ``detail`` роутер отдаёт как есть."""

    def __init__(self, message: str, status: int = 400, detail: object | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.detail = message if detail is None else detail


def month_days(month: str) -> list[str]:
    year, mon = int(month[:4]), int(month[5:7])
    return [f"{month}-{day:02d}" for day in range(1, monthrange(year, mon)[1] + 1)]


def calendar_for(slug: str, master_id: str, month: str) -> dict:
    """Месяц графика одного мастера: что даёт недельная сетка и чем её правили."""
    rt = runtime.for_tenant(slug)
    tenant = rt.tenant
    master = tenant.master(master_id)
    if not master:
        raise ShiftError("Мастера нет", 404)

    tz_name = tenant.timezone
    today = today_key(tz_name)
    month = month or today[:7]
    dates = month_days(month)

    # Записи месяца одним запросом: тридцать отдельных — тридцать походов в базу
    # ради числа в углу ячейки.
    span_start = zoned(dates[0], "00:00", tz_name)
    span_end = zoned((parse_date(dates[-1]) + timedelta(days=1)).isoformat(), "00:00", tz_name)
    counts: dict[str, int] = {}
    for booking in rt.tools.store.day_bookings(tenant_id=slug, start=span_start, end=span_end):
        if booking.master_id != master_id:
            continue
        key = booking.start_at.astimezone(span_start.tzinfo).date().isoformat()
        counts[key] = counts.get(key, 0) + 1

    days = []
    for date_str in dates:
        shift = shift_of(master, date_str)
        hours = work_hours(tenant, master, date_str)
        days.append({
            "date": date_str,
            "works": working_day(tenant, master, date_str),
            "start": hours["start"] or "",
            "end": hours["end"] or "",
            # custom — своя смена на этот день, off — выходной поверх сетки,
            # week — день живёт по недельной сетке мастера.
            "source": ("off" if shift.get("off") else "custom") if shift else "week",
            "bookings": counts.get(date_str, 0),
            "past": date_str < today,
        })

    return {
        "month": month,
        "today": today,
        "masterId": master_id,
        "master": master["name"],
        "workDays": [int(d) for d in (master.get("workDays") or tenant.salon.get("workDays") or [])],
        "weekHours": {"start": (master.get("workHours") or {}).get("start") or "",
                      "end": (master.get("workHours") or {}).get("end") or ""},
        "salonHours": tenant.salon.get("workHours") or {},
        "days": days,
    }


def set_shift(slug: str, master_id: str, *, date: str, mode: str, start: str = "",
              end: str = "", force: bool = False) -> dict:
    """Один день графика. Возвращает пересчитанный месяц — экран не гадает."""
    rt = runtime.for_tenant(slug)
    tenant = rt.tenant
    if not tenant.master(master_id):
        raise ShiftError("Мастера нет", 404)
    if date < today_key(tenant.timezone):
        raise ShiftError("Прошедший день менять нечего")

    start, end = start.strip(), end.strip()
    shift: dict | None
    if mode == "default":
        shift = None
    elif mode == "off":
        shift = {"off": True}
    else:
        if bool(start) != bool(end):
            raise ShiftError("Укажите и начало, и конец смены")
        for value in (start, end):
            if value and not re.fullmatch(TIME_PATTERN, value):
                raise ShiftError("Время в формате ЧЧ:ММ")
        if start and end:
            if start >= end:
                raise ShiftError("Конец смены должен быть позже начала")
            salon = tenant.salon.get("workHours") or {}
            if salon.get("start") and start < salon["start"]:
                raise ShiftError(f"Салон открывается в {salon['start']}")
            if salon.get("end") and end > salon["end"]:
                raise ShiftError(f"Салон закрывается в {salon['end']}")
        shift = {"start": start, "end": end} if start else {"off": False}

    # Записи на этот день не исчезают от того, что мастер объявил выходной, —
    # их надо перенести руками. Поэтому спрашиваем подтверждение, а не молчим.
    if mode == "off" and not force:
        day_start = zoned(date, "00:00", tenant.timezone)
        day_end = zoned(date, "23:59", tenant.timezone)
        booked = [b for b in rt.tools.store.day_bookings(tenant_id=slug, start=day_start,
                                                         end=day_end)
                  if b.master_id == master_id]
        if booked:
            raise ShiftError("На этот день уже есть записи", 409, {
                "error": "На этот день уже есть записи", "bookings": len(booked),
            })

    try:
        tenant.set_master_shift(master_id, date, shift)
    except TenantError as exc:
        raise ShiftError(str(exc)) from exc
    log.info("[%s] график %s на %s: %s", slug, master_id, date, mode)
    return calendar_for(slug, master_id, date[:7])
