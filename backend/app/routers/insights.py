"""Рабочие экраны владельца: статистика, расписание, диалоги, тариф.

Настройки отвечают на вопрос «как бот устроен», эти экраны — на вопрос
«что он сделал за неделю и что происходит сегодня».
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..billing import LimitExceeded, PLANS, account, snapshot
from ..events import event as log_event
from ..calendar_service import CalendarError
from ..db import BOOKING_STATUSES
from ..deps import runtime
from ..slots import shift_of, work_hours
from ..tenants import registry
from ..timeutil import DATE_PATTERN, human_date, now, parse_date, today_key, zoned
from .admin import guard, tenant_slug

log = logging.getLogger("insights")
router = APIRouter(prefix="/api/admin", tags=["insights"])


# --- статистика --------------------------------------------------------------

@router.get("/stats", dependencies=[Depends(guard)])
def stats(days: int = Query(default=30, ge=1, le=365), slug: str = Depends(tenant_slug)) -> dict:
    rt = runtime.for_tenant(slug)
    store = rt.tools.store
    since = datetime.now(timezone.utc) - timedelta(days=days)

    data = store.booking_stats(tenant_id=slug, since=since)
    dialogs = data["conversations"]
    bookings = data["bookings"]
    active = data["confirmed"] + data["completed"]

    # Проценты считаем здесь: в панели должно быть видно, а не «посчитайте сами».
    data["conversionPct"] = round(data["conversationsWithBooking"] / dialogs * 100, 1) if dialogs else 0.0
    data["cancelledPct"] = round(data["cancelled"] / bookings * 100, 1) if bookings else 0.0
    data["noShowPct"] = round(data["noShow"] / bookings * 100, 1) if bookings else 0.0
    data["successful"] = active
    data["byService"] = [
        {**row, "title": (rt.tenant.service(row["id"]) or {}).get("title", row["id"])}
        for row in data["byService"]
    ]
    data["byMaster"] = [
        {**row, "title": (rt.tenant.master(row["id"]) or {}).get("name", row["id"])}
        for row in data["byMaster"]
    ]
    return {
        "days": days,
        "stats": data,
        "daily": store.daily_bookings(tenant_id=slug, since=since),
        "usage": snapshot(store, tenants=registry.slugs())["usage"],
    }


# --- расписание --------------------------------------------------------------

@router.get("/schedule", dependencies=[Depends(guard)])
def schedule(date: str = Query(default="", pattern=f"^({DATE_PATTERN})?$"),
             slug: str = Depends(tenant_slug)) -> dict:
    """Один день по всем мастерам: записи бота и занятость их Google-календарей."""
    rt = runtime.for_tenant(slug)
    tenant = rt.tenant
    date_str = date or today_key(tenant.timezone)
    hours = tenant.salon.get("workHours", {"start": "10:00", "end": "20:00"})
    day_start = zoned(date_str, hours["start"], tenant.timezone)
    day_end = zoned(date_str, hours["end"], tenant.timezone)

    own = {}
    for booking in rt.tools.store.day_bookings(tenant_id=slug, start=day_start, end=day_end):
        own.setdefault(booking.master_id, []).append(booking)

    columns = []
    for master in tenant.masters:
        events = [
            {
                "kind": "booking",
                "start": b.start_at.astimezone(day_start.tzinfo).strftime("%H:%M"),
                "end": b.end_at.astimezone(day_start.tzinfo).strftime("%H:%M"),
                "title": (tenant.service(b.service_id) or {}).get("title", b.service_id),
                "client": b.client_name,
                "phone": b.phone,
                "status": b.status,
                "requiresConfirmation": bool(b.requires_confirmation),
                "bookingId": b.id,
            }
            for b in own.get(master["id"], [])
        ]

        external, error = [], ""
        if rt.calendar.mode == "google":
            try:
                own_spans = {(b.start_at, b.end_at) for b in own.get(master["id"], [])}
                for start, end in rt.calendar.busy(master, day_start, day_end):
                    if (start, end) in own_spans:
                        continue  # это наша же запись, не дублируем
                    external.append({
                        "kind": "external",
                        "start": start.astimezone(day_start.tzinfo).strftime("%H:%M"),
                        "end": end.astimezone(day_start.tzinfo).strftime("%H:%M"),
                        "title": "Занято в Google Calendar",
                    })
            except CalendarError as exc:
                error = "Календарь недоступен"
                log.error("Расписание %s: %s", master["id"], exc)

        columns.append({
            "masterId": master["id"],
            "master": master["name"],
            "calendarId": master.get("calendarId", "primary"),
            "worksToday": _works(tenant, master, date_str),
            # Смена мастера, уже с подставленными часами салона там, где пусто,
            # и с правкой из календаря смен, если она на этот день есть.
            "workHours": work_hours(tenant, master, date_str),
            "shift": shift_of(master, date_str),
            "events": sorted(events + external, key=lambda e: e["start"]),
            "error": error,
        })

    return {
        "date": date_str,
        "dateLabel": "сегодня" if date_str == today_key(tenant.timezone) else human_date(date_str),
        "workHours": hours,
        "calendarMode": rt.calendar.mode,
        "columns": columns,
    }


def _works(tenant, master: dict, date_str: str) -> bool:
    from ..slots import working_day

    return working_day(tenant, master, date_str)


# --- расписание: диапазон дней ------------------------------------------------

# Сколько дней разрешено запросить разом. Месяц с хвостами недели — 42 клетки,
# больше сетке не нужно, а без потолка один запрос легко уводит панель в минуту
# ожидания на чужом Google-календаре.
RANGE_LIMIT_DAYS = 45


@router.get("/schedule/range", dependencies=[Depends(guard)])
def schedule_range(
    date_from: str = Query(alias="from", pattern=DATE_PATTERN),
    date_to: str = Query(alias="to", pattern=DATE_PATTERN),
    calendar: bool = Query(default=True),
    slug: str = Depends(tenant_slug),
) -> dict:
    """Несколько дней сразу — данные для сетки «часы по вертикали, дни по горизонтали».

    Отдельный эндпоинт, а не цикл по ``/schedule`` на фронте: занятость Google
    берётся одним запросом freebusy на мастера за весь период, а не по запросу
    на каждый день. Для недели это семь обращений к чужому API против одного,
    для месяца — тридцать против одного.

    ``calendar=0`` пропускает Google целиком: в масштабе месяца полосы чужой
    занятости всё равно нечитаемы, а ждать ради них незачем.
    """
    rt = runtime.for_tenant(slug)
    tenant = rt.tenant
    start_date, end_date = parse_date(date_from), parse_date(date_to)
    if end_date < start_date:
        raise HTTPException(422, "Конец периода раньше начала")
    span = (end_date - start_date).days + 1
    if span > RANGE_LIMIT_DAYS:
        raise HTTPException(422, f"Период больше {RANGE_LIMIT_DAYS} дней")

    dates = [(start_date + timedelta(days=i)).isoformat() for i in range(span)]
    # Границы берём по суткам, а не по часам салона: запись, случайно
    # заведённая до открытия, должна быть видна владельцу, а не исчезать.
    span_start = zoned(dates[0], "00:00", tenant.timezone)
    span_end = zoned(dates[-1], "00:00", tenant.timezone) + timedelta(days=1)
    tzinfo = span_start.tzinfo

    own: dict[str, dict[str, list]] = {}
    for booking in rt.tools.store.day_bookings(tenant_id=slug, start=span_start, end=span_end):
        local = booking.start_at.astimezone(tzinfo)
        own.setdefault(local.date().isoformat(), {}).setdefault(booking.master_id, []).append(booking)

    # Технические перерывы — такая же занятость мастера, как записи, и в журнале
    # они должны быть видны: иначе администратор ставит клиента в обед, а сетка
    # окон при этом молчит, потому что окно уже вычтено.
    blocks: dict[str, dict[str, list]] = {}
    for block in runtime.store.time_blocks(tenant_id=slug, start=span_start, end=span_end):
        local = block.start_at.astimezone(tzinfo)
        blocks.setdefault(local.date().isoformat(), {}).setdefault(block.master_id, []).append(block)

    use_google = calendar and rt.calendar.mode == "google"
    busy: dict[str, list[tuple]] = {}
    errors: dict[str, str] = {}
    if use_google:
        for master in tenant.masters:
            try:
                busy[master["id"]] = rt.calendar.busy(master, span_start, span_end)
            except CalendarError as exc:
                errors[master["id"]] = "Календарь недоступен"
                log.error("Расписание %s %s–%s: %s", master["id"], dates[0], dates[-1], exc)

    today = today_key(tenant.timezone)
    days = []
    for date_str in dates:
        day_start = zoned(date_str, "00:00", tenant.timezone)
        day_end = day_start + timedelta(days=1)
        columns = []
        for master in tenant.masters:
            mine = own.get(date_str, {}).get(master["id"], [])
            events = [_booking_event(tenant, b, tzinfo) for b in mine]
            own_spans = {(b.start_at, b.end_at) for b in mine}
            for ev_start, ev_end in busy.get(master["id"], []):
                if ev_end <= day_start or ev_start >= day_end:
                    continue
                if (ev_start, ev_end) in own_spans:
                    continue  # это наша же запись, не дублируем
                events.append({
                    "kind": "external",
                    # Событие может перетекать через полночь — в сетке дня
                    # показываем ту часть, которая в этот день и попадает.
                    "start": max(ev_start, day_start).astimezone(tzinfo).strftime("%H:%M"),
                    "end": _clip_end(min(ev_end, day_end), day_start, tzinfo),
                    "title": "Занято в Google Calendar",
                })
            for block in blocks.get(date_str, {}).get(master["id"], []):
                events.append({
                    "kind": "break", "blockId": block.id, "title": block.title,
                    "start": max(block.start_at, day_start).astimezone(tzinfo).strftime("%H:%M"),
                    "end": _clip_end(min(block.end_at, day_end), day_start, tzinfo),
                })
            columns.append({
                "masterId": master["id"],
                "worksToday": _works(tenant, master, date_str),
                "workHours": work_hours(tenant, master, date_str),
                "shift": shift_of(master, date_str),
                "events": sorted(events, key=lambda e: e["start"]),
                "error": errors.get(master["id"], ""),
            })
        days.append({
            "date": date_str,
            "dateLabel": "сегодня" if date_str == today else human_date(date_str),
            "isToday": date_str == today,
            "columns": columns,
        })

    return {
        "from": dates[0],
        "to": dates[-1],
        "workHours": tenant.salon.get("workHours", {"start": "10:00", "end": "20:00"}),
        "calendarMode": rt.calendar.mode,
        # Мастера — один раз на весь ответ: в сетке месяца иначе тридцать копий
        # одного и того же списка имён.
        "masters": [
            {"id": m["id"], "name": m["name"], "role": m.get("role", "")}
            for m in tenant.masters
        ],
        "days": days,
        "now": now(tenant.timezone).strftime("%H:%M"),
    }


def _booking_event(tenant, b, tzinfo) -> dict:
    return {
        "kind": "booking",
        "start": b.start_at.astimezone(tzinfo).strftime("%H:%M"),
        "end": b.end_at.astimezone(tzinfo).strftime("%H:%M"),
        "title": (tenant.service(b.service_id) or {}).get("title", b.service_id),
        "client": b.client_name,
        "phone": b.phone,
        "status": b.status,
        "requiresConfirmation": bool(b.requires_confirmation),
        "bookingId": b.id,
    }


def _clip_end(end, day_start, tzinfo) -> str:
    """Конец события в этих сутках. Полночь следующего дня — это «24:00».

    Без этого событие, тянущееся до утра, рисовалось бы полоской нулевой высоты
    в самом верху сетки: «00:00» в дне означает начало, а не конец.
    """
    return "24:00" if end >= day_start + timedelta(days=1) else end.astimezone(tzinfo).strftime("%H:%M")


# --- диалоги -----------------------------------------------------------------

@router.get("/conversations", dependencies=[Depends(guard)])
def conversations(limit: int = Query(default=50, ge=1, le=200), offset: int = 0,
                  slug: str = Depends(tenant_slug)) -> dict:
    store = runtime.for_tenant(slug).tools.store
    return {"conversations": store.list_conversations(tenant_id=slug, limit=limit, offset=offset)}


@router.get("/conversations/{conversation_id}", dependencies=[Depends(guard)])
def conversation(conversation_id: str, slug: str = Depends(tenant_slug)) -> dict:
    """Диалог целиком: переписка и всё, что известно о записях из неё.

    Названия услуги и мастера, цену и длительность подставляем здесь: в базе
    лежат только идентификаторы, а справочник живёт в конфигурации бизнеса.
    Уведомления кладём рядом с записью — владельцу важно видеть не только сам
    визит, но и дошло ли до клиента подтверждение и напоминание.
    """
    rt = runtime.for_tenant(slug)
    store = rt.tools.store
    detail = store.conversation_detail(conversation_id, tenant_id=slug)
    if not detail:
        raise HTTPException(404, "Диалог не найден")

    for b in detail["bookings"]:
        service = rt.tenant.service(b["service"]) or {}
        master = rt.tenant.master(b["master"]) or {}
        b["serviceId"], b["masterId"] = b["service"], b["master"]
        b["service"] = service.get("title") or b["service"]
        b["master"] = master.get("name") or b["master"]
        b["price"] = service.get("price") or ""
        b["duration"] = service.get("duration") or 0
        b["masterRole"] = master.get("role") or ""
        b["notifications"] = [n.as_dict() for n in
                              store.list_notifications(tenant_id=slug, booking_id=b["id"], limit=50)]
    return detail


# --- статусы визитов ---------------------------------------------------------

class StatusPatch(BaseModel):
    status: str


@router.post("/bookings/{booking_id}/status", dependencies=[Depends(guard)])
def set_status(booking_id: str, payload: StatusPatch, slug: str = Depends(tenant_slug)) -> dict:
    """«Пришёл / не пришёл» — на этом строится учёт неявок."""
    if payload.status not in BOOKING_STATUSES:
        raise HTTPException(422, f"Статус должен быть одним из: {', '.join(BOOKING_STATUSES)}")
    rt = runtime.for_tenant(slug)
    booking = rt.tools.store.set_booking_status(booking_id, payload.status, tenant_id=slug)
    if not booking:
        raise HTTPException(404, "Запись не найдена")

    if payload.status == "cancelled" and rt.tools.notifications:
        rt.tools.notifications.cancel_for_booking(booking.id, reason="cancelled_by_admin")
        # Отменяет салон, а приходит клиент: без этого сообщения он узнаёт об
        # отмене у закрытой двери.
        rt.tools.notifications.notify_client_cancelled(booking, rt.tenant)
        rt.tools.notifications.notify_master_cancelled(booking, rt.tenant)
        rt.tools.notifications.offer_waitlist(booking, rt.tenant)
    if payload.status == "completed" and rt.tools.notifications:
        rt.tools.notifications.schedule_review(booking, rt.tenant)
    if payload.status == "completed" and booking.client_id and rt.tenant.salon.get("loyaltyEnabled"):
        percent = max(0, int(rt.tenant.salon.get("loyaltyPercent") or 0))
        points = int(booking.paid_amount or 0) * percent // 100
        if points:
            rt.tools.store.change_loyalty(
                tenant_id=slug, client_id=booking.client_id, points=points,
                reason="Кэшбэк за визит", booking_id=booking.id, idempotent=True)

    no_shows = 0
    if payload.status == "no_show":
        window = int(rt.tenant.policy("noShowWindowDays", 180) or 180)
        no_shows = rt.tools.store.no_show_count(
            booking.phone, tenant_id=slug,
            since=datetime.now(timezone.utc) - timedelta(days=window))
    log_event("booking.status", tenant=slug, booking=booking_id, status=booking.status,
              master=booking.master_id, service=booking.service_id)
    return {"ok": True, "status": booking.status, "noShowCount": no_shows,
            "limit": int(rt.tenant.policy("noShowLimit", 3) or 0)}


# --- тариф -------------------------------------------------------------------

class PlanPatch(BaseModel):
    plan: str
    status: str = "active"
    customerEmail: str = ""  # noqa: N815
    renewsAt: str = ""  # noqa: N815


@router.get("/billing", dependencies=[Depends(guard)])
def billing() -> dict:
    return snapshot(runtime.store, tenants=registry.slugs())


@router.put("/billing", dependencies=[Depends(guard)])
def update_billing(payload: PlanPatch) -> dict:
    """Смена тарифа. Провайдер оплаты подключается сюда же вебхуком."""
    if payload.plan not in PLANS:
        raise HTTPException(422, f"Неизвестный тариф «{payload.plan}»")
    if payload.status not in ("active", "past_due", "cancelled"):
        raise HTTPException(422, "Статус подписки: active, past_due или cancelled")

    limit = PLANS[payload.plan]["limits"]["tenants"]
    if limit != -1 and len(registry.slugs()) > limit:
        raise HTTPException(422, f"Сейчас {len(registry.slugs())} бизнесов — тариф «"
                                 f"{PLANS[payload.plan]['title']}» допускает {limit}. "
                                 "Удалите лишние бизнесы или выберите тариф выше.")
    account.save({"plan": payload.plan, "status": payload.status,
                  "customerEmail": payload.customerEmail, "renewsAt": payload.renewsAt})
    return snapshot(runtime.store, tenants=registry.slugs())
