"""Кабинет мастера: свой день, своя неделя, свой график.

Отдельный экран, а не раздел панели, по двум причинам. Первая — права: панель
показывает выручку салона, клиентскую базу, ключи интеграций и настройки, и
пускать туда мастера нельзя. Вторая — телефон: мастер смотрит расписание между
клиентами, стоя, одной рукой, и ему нужны сегодняшние записи, а не таблица на
двадцать колонок.

Всё API отвечает только про одного мастера — того, чья сессия пришла в cookie.
Идентификатор мастера в запросах не принимается вовсе: иначе достаточно было бы
подставить чужой, чтобы посмотреть чужой день.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from .. import staff
from ..auth import cookie_is_secure
from ..calendar_service import CalendarError
from ..deps import runtime
from ..events import event as log_event
from ..policies import RateLimiter
from ..shifts import MONTH_PATTERN, ShiftError, calendar_for, set_shift
from ..slots import work_hours, working_day
from ..timeutil import DATE_PATTERN, TIME_PATTERN, parse_date, today_key, tz, zoned

log = logging.getLogger("team")
router = APIRouter(prefix="/api/team", tags=["team"])

ENTER_ATTEMPTS_PER_MINUTE = 10
_attempts = RateLimiter()


class Enter(BaseModel):
    key: str
    pin: str = ""


class ShiftUpdate(BaseModel):
    date: str = Field(pattern=DATE_PATTERN)
    mode: str = Field(pattern="^(default|off|work)$")
    start: str = ""
    end: str = ""
    force: bool = False


class BreakCreate(BaseModel):
    date: str = Field(pattern=DATE_PATTERN)
    start: str = Field(pattern=TIME_PATTERN)
    end: str = Field(pattern=TIME_PATTERN)
    title: str = "Перерыв"


class Master:
    """Кто пришёл: бизнес, идентификатор мастера и его карточка."""

    def __init__(self, slug: str, master_id: str, card: dict) -> None:
        self.slug, self.id, self.card = slug, master_id, card


def current(request: Request) -> Master | None:
    """Мастер текущей сессии или None. Ошибку не бросает: тем же кодом
    пользуется страница, которой нужно просто узнать, вошли мы или нет."""
    found = staff.session_master(runtime.store, request.cookies.get(staff.SESSION_COOKIE))
    if not found:
        return None
    slug, master_id = found
    try:
        card = runtime.for_tenant(slug).tenant.master(master_id)
    except Exception:  # noqa: BLE001 — бизнес мог быть удалён вместе с конфигом
        return None
    # Мастера могли убрать из салона — ссылка при этом остаётся живой.
    return Master(slug, master_id, card) if card else None


def require(request: Request) -> Master:
    master = current(request)
    if not master:
        raise HTTPException(401, "Нужно открыть личную ссылку заново")
    return master


def _client(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.post("/start")
def start(payload: Enter, request: Request) -> dict:
    """Первый шаг: что спросить у мастера — придумать ПИН или ввести его.

    Экран должен знать это до ввода, иначе он либо просит придумать ПИН у того,
    кто его уже задал, либо наоборот. Имя мастера отдаём здесь же: человек,
    открывший ссылку, должен видеть, куда попал.
    """
    if not _attempts.allow(f"team-start:{_client(request)}", ENTER_ATTEMPTS_PER_MINUTE):
        raise HTTPException(429, "Слишком много попыток — подождите минуту")
    try:
        stage, slug, master_id = staff.stage_of(runtime.store, payload.key.strip())
    except staff.StaffError as exc:
        raise HTTPException(exc.status, str(exc)) from exc

    tenant = runtime.for_tenant(slug).tenant
    card = tenant.master(master_id) or {}
    return {
        "stage": stage,
        "master": card.get("name") or master_id,
        "salon": tenant.salon.get("name") or tenant.title,
    }


@router.post("/enter")
def enter(payload: Enter, request: Request, response: Response) -> dict:
    """Вход по личной ссылке и ПИНу. Ключ уходит телом запроса, а не остаётся в
    адресе: из адресной строки он попадает и в историю браузера, и в чужие логи.

    Если ПИН ещё не задан, этот же запрос его и задаёт — мастер придумывает
    четыре цифры при первом входе.
    """
    if not _attempts.allow(f"team-enter:{_client(request)}", ENTER_ATTEMPTS_PER_MINUTE):
        raise HTTPException(429, "Слишком много попыток — подождите минуту")
    try:
        token, slug, master_id = staff.open_session(runtime.store, payload.key.strip(),
                                                    payload.pin.strip())
    except staff.StaffError as exc:
        raise HTTPException(exc.status, str(exc)) from exc

    response.set_cookie(
        staff.SESSION_COOKIE, token,
        max_age=int(staff.SESSION_TTL.total_seconds()),
        httponly=True, secure=cookie_is_secure(), samesite="lax", path="/",
    )
    log_event("team.enter", tenant=slug, master=master_id)
    return _state_payload(slug, master_id)


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    staff.close_session(runtime.store, request.cookies.get(staff.SESSION_COOKIE))
    response.delete_cookie(staff.SESSION_COOKIE, path="/")
    return {"ok": True}


def _state_payload(slug: str, master_id: str) -> dict:
    tenant = runtime.for_tenant(slug).tenant
    card = tenant.master(master_id) or {}
    return {
        "authenticated": True,
        "master": card.get("name") or master_id,
        "role": card.get("role") or "",
        "salon": tenant.salon.get("name") or tenant.title,
        "timezone": tenant.timezone,
        "today": today_key(tenant.timezone),
        "salonHours": tenant.salon.get("workHours") or {},
    }


@router.get("/state")
def state(request: Request) -> dict:
    master = current(request)
    if not master:
        return {"authenticated": False}
    return _state_payload(master.slug, master.id)


def _span_dates(span: str, date_str: str) -> list[str]:
    """Какие дни показываем. Неделя считается от понедельника — так её видит
    мастер в календаре телефона, и «неделя с сегодня» сбивала бы с толку."""
    day = parse_date(date_str)
    if span == "day":
        return [day.isoformat()]
    if span == "week":
        first = day - timedelta(days=day.weekday())
        return [(first + timedelta(days=i)).isoformat() for i in range(7)]
    from calendar import monthrange

    last = monthrange(day.year, day.month)[1]
    return [f"{day.year:04d}-{day.month:02d}-{i:02d}" for i in range(1, last + 1)]


@router.get("/agenda")
def agenda(request: Request, span: str = Query(default="day", pattern="^(day|week|month)$"),
           date: str = Query(default="", pattern=f"^({DATE_PATTERN})?$")) -> dict:
    """Кто записан: день, неделя или месяц — только к этому мастеру.

    Дни отдаём все подряд, включая выходные и пустые: сетка на экране не должна
    ехать от того, что в среду никого нет.
    """
    master = require(request)
    rt = runtime.for_tenant(master.slug)
    tenant = rt.tenant
    tz_name = tenant.timezone
    zone = tz(tz_name)
    dates = _span_dates(span, date or today_key(tz_name))

    start = zoned(dates[0], "00:00", tz_name)
    end = zoned((parse_date(dates[-1]) + timedelta(days=1)).isoformat(), "00:00", tz_name)

    by_day: dict[str, list[dict]] = {d: [] for d in dates}
    for b in runtime.store.day_bookings(tenant_id=master.slug, start=start, end=end):
        if b.master_id != master.id:
            continue
        local = b.start_at.astimezone(zone)
        key = local.date().isoformat()
        if key not in by_day:
            continue
        service = tenant.service(b.service_id) or {}
        by_day[key].append({
            "id": b.id,
            "start": local.strftime("%H:%M"),
            "end": b.end_at.astimezone(zone).strftime("%H:%M"),
            "service": service.get("title") or b.service_id,
            "client": b.client_name,
            # Телефон мастеру нужен, чтобы позвонить опаздывающему, — это
            # ровно та причина, по которой он вообще открывает этот экран.
            "phone": b.phone,
            "comment": b.comment or "",
            "status": b.status,
            "price": b.price_amount,
            "currency": b.currency or "",
            "groupSize": b.group_size or 1,
        })

    blocks: dict[str, list[dict]] = {d: [] for d in dates}
    for row in runtime.store.time_blocks(tenant_id=master.slug, start=start, end=end,
                                         master_id=master.id):
        local = row.start_at.astimezone(zone)
        key = local.date().isoformat()
        if key in blocks:
            blocks[key].append({
                "id": row.id, "title": row.title,
                "start": local.strftime("%H:%M"),
                "end": row.end_at.astimezone(zone).strftime("%H:%M"),
            })

    days = []
    for date_str in dates:
        hours = work_hours(tenant, master.card, date_str)
        items = sorted(by_day[date_str], key=lambda x: x["start"])
        days.append({
            "date": date_str,
            "works": working_day(tenant, master.card, date_str),
            "start": hours["start"] or "",
            "end": hours["end"] or "",
            "bookings": items,
            "blocks": sorted(blocks[date_str], key=lambda x: x["start"]),
            "count": len(items),
            # Сумма — только по записям с проставленной ценой: сложить
            # «от 900 UYU» нельзя, а показать вместо этого ноль значит соврать.
            "amount": sum(x["price"] or 0 for x in items),
        })

    return {"span": span, "today": today_key(tz_name), "master": master.card.get("name", master.id),
            "days": days}


@router.get("/shifts")
def shifts(request: Request,
           month: str = Query(default="", pattern=f"^({MONTH_PATTERN})?$")) -> dict:
    """Свой график на месяц: где недельная сетка, а где правка на дату."""
    master = require(request)
    try:
        return calendar_for(master.slug, master.id, month)
    except ShiftError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@router.put("/shifts")
def put_shift(payload: ShiftUpdate, request: Request) -> dict:
    """Правка своего графика на один день — то же, что делает владелец в панели."""
    master = require(request)
    try:
        result = set_shift(master.slug, master.id, date=payload.date, mode=payload.mode,
                           start=payload.start, end=payload.end, force=payload.force)
    except ShiftError as exc:
        raise HTTPException(exc.status, exc.detail) from exc
    log_event("team.shift", tenant=master.slug, master=master.id,
              date=payload.date, mode=payload.mode)
    return result


@router.post("/breaks")
def add_break(payload: BreakCreate, request: Request) -> dict:
    """Перерыв в своём дне: обед, дорога, личное дело. Занимает время так же,
    как запись, и попадает в календарь мастера."""
    master = require(request)
    rt = runtime.for_tenant(master.slug)
    tenant = rt.tenant
    if payload.start >= payload.end:
        raise HTTPException(400, "Конец перерыва должен быть позже начала")

    start = zoned(payload.date, payload.start, tenant.timezone)
    end = zoned(payload.date, payload.end, tenant.timezone)
    # Поверх записи перерыв не ставим: клиент уже придёт, и «обед» на этом месте
    # означал бы, что кто-то один останется в дверях.
    clash = runtime.store.overlapping(master.id, start, end, tenant_id=master.slug)
    if clash:
        raise HTTPException(409, detail={"error": "На это время уже есть запись",
                                         "bookings": len(clash)})

    row = runtime.store.add_time_block(tenant_id=master.slug, master_id=master.id,
                                       start_at=start, end_at=end,
                                       title=payload.title.strip() or "Перерыв")
    warning = ""
    try:
        event = rt.calendar.create_block(master=master.card, title=row.title, start=start, end=end)
        runtime.store.attach_block_event(row.id, event["id"])
    except CalendarError as exc:
        log.error("[%s] перерыв %s не попал в календарь: %s", master.slug, row.id, exc)
        warning = "Перерыв сохранён, но в календарь не попал"
    log_event("team.break", tenant=master.slug, master=master.id, date=payload.date)
    return {"ok": True, "warning": warning}


@router.delete("/breaks/{block_id}")
def drop_break(block_id: str, request: Request) -> dict:
    """Снимает свой перерыв. Чужой снять нельзя — проверка по мастеру сессии."""
    master = require(request)
    rt = runtime.for_tenant(master.slug)
    row = runtime.store.get_time_block(block_id, tenant_id=master.slug)
    if not row or row.master_id != master.id:
        raise HTTPException(404, "Перерыв не найден")

    warning = ""
    if row.calendar_event_id:
        try:
            rt.calendar.delete_event(master.card, row.calendar_event_id)
        except CalendarError as exc:
            # Иначе в календаре мастера останется висеть призрак обеда.
            log.error("[%s] событие перерыва %s не снялось: %s", master.slug, block_id, exc)
            warning = "Перерыв снят, но в календаре событие осталось"
    runtime.store.drop_time_block(block_id, tenant_id=master.slug)
    return {"ok": True, "warning": warning}
