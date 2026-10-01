"""Админ-API: список бизнесов, их создание и конфигурация каждого."""

from __future__ import annotations

import hmac
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from .. import ai_providers, auth, google_oauth, staff, telegram, telegram_bot, twilio_api
from ..billing import LimitExceeded, check_can_add_tenant
from ..deps import runtime
from ..policies import RateLimiter, master_link_code, webhook_secret
from ..schema import SCHEMA, validate_config
from ..settings import admin_open, admin_token
from ..shifts import MONTH_PATTERN, ShiftError, calendar_for, set_shift
from ..tenants import TenantError, registry
from ..timeutil import DATE_PATTERN, TIME_PATTERN, tz, utc_iso, zoned

log = logging.getLogger("admin")
router = APIRouter(prefix="/api/admin", tags=["admin"])

ADMIN_ATTEMPTS_PER_MINUTE = 10
_attempts = RateLimiter()


def guard(request: Request, x_admin_token: str | None = Header(default=None)) -> None:
    """Доступ к админке: сессия пользователя или машинный токен.

    Людям — вход по почте и паролю (cookie сессии), скриптам — ``X-Admin-Token``.
    Токен не отзывается и не различает, кто им воспользовался, поэтому для
    браузера он больше не предлагается, но ломать им интеграции незачем.

    Сравнение токена — постоянного времени, чтобы его нельзя было подобрать по
    времени ответа; неудачные попытки ограничены по частоте.
    """
    if auth.session_user(runtime.store, request.cookies.get(auth.SESSION_COOKIE)):
        return

    token = admin_token()
    if not token:
        if admin_open():
            return
        # Пока не создан первый администратор, панель должна дать себя настроить,
        # иначе войти в неё нельзя ничем.
        if not auth.users_exist(runtime.store):
            raise HTTPException(401, "Создайте администратора")
        raise HTTPException(401, "Нужен вход")

    if not hmac.compare_digest((x_admin_token or "").encode("utf-8", "ignore"), token.encode()):
        if not _attempts.allow("admin-auth", ADMIN_ATTEMPTS_PER_MINUTE):
            raise HTTPException(429, "Слишком много попыток — подождите минуту")
        raise HTTPException(401, "Нужен вход")


def owner_only(request: Request, x_admin_token: str | None = Header(default=None)) -> None:
    """Подключения, ключи и список пользователей — только владелец.

    Спрятать раздел в панели недостаточно: администратор открыл бы тот же
    эндпоинт напрямую. Машинный токен приравнен к владельцу — он и есть доступ
    уровня сервера, а не роль конкретного человека.
    """
    user = auth.session_user(runtime.store, request.cookies.get(auth.SESSION_COOKIE))
    if user:
        if user.role != "owner":
            raise HTTPException(403, "Раздел доступен только владельцу")
        return
    guard(request, x_admin_token)


def tenant_slug(tenant: str | None = Query(default=None)) -> str:
    slugs = registry.slugs()
    slug = tenant or (slugs[0] if slugs else None)
    if not slug or not registry.exists(slug):
        raise HTTPException(404, "Бизнес не найден")
    return slug


# --- бизнесы -----------------------------------------------------------------

class CreateTenant(BaseModel):
    slug: str
    title: str = ""
    copyFrom: str | None = None  # noqa: N815 — контракт с формой


class OnboardingTenant(CreateTenant):
    salon: dict = Field(default_factory=dict)
    services: list[dict] = Field(default_factory=list)
    masters: list[dict] = Field(default_factory=list)


@router.get("/tenants", dependencies=[Depends(guard)])
def list_tenants() -> dict:
    return {"tenants": registry.list()}


@router.post("/tenants", dependencies=[Depends(guard)])
def create_tenant(payload: CreateTenant) -> dict:
    try:
        check_can_add_tenant(len(registry.slugs()))
    except LimitExceeded as exc:
        raise HTTPException(402, exc.message) from exc
    try:
        tenant = registry.create(payload.slug, payload.title, copy_from=payload.copyFrom)
    except TenantError as exc:
        raise HTTPException(422, str(exc)) from exc
    runtime.forget(tenant.slug)
    log.info("Создан бизнес %s", tenant.slug)
    return {"ok": True, "tenant": tenant.slug, "tenants": registry.list()}


@router.post("/onboarding", dependencies=[Depends(guard)])
def onboarding(payload: OnboardingTenant) -> dict:
    """Создаёт готовый бизнес из структурированной анкеты одним запросом."""
    created = create_tenant(CreateTenant(slug=payload.slug, title=payload.title,
                                         copyFrom=payload.copyFrom))
    tenant = registry.get(payload.slug)
    form = tenant.form_data()
    form["salon"] = {**form.get("salon", {}), **payload.salon}
    if payload.services:
        form["services"] = payload.services
    if payload.masters:
        form["masters"] = payload.masters
    ok, errors = tenant.save_form(form)
    if not ok:
        registry.delete(payload.slug)
        runtime.forget(payload.slug)
        raise HTTPException(422, detail={"ok": False, "errors": errors})
    runtime.reload(payload.slug)
    return {**created, "configured": True, "publicBookingPath": f"/book/{payload.slug}"}


@router.delete("/tenants/{slug}", dependencies=[Depends(guard)])
def delete_tenant(slug: str) -> dict:
    try:
        registry.delete(slug)
    except TenantError as exc:
        raise HTTPException(422, str(exc)) from exc
    runtime.forget(slug)
    log.info("Удалён бизнес %s", slug)
    return {"ok": True, "tenants": registry.list()}


# --- конфигурация бизнеса ----------------------------------------------------

@router.get("/schema", dependencies=[Depends(guard)])
def get_schema() -> dict:
    return {"schema": SCHEMA}


def remember_public_base(tenant, request: Request) -> None:
    """Запоминает публичный адрес сервиса по тому, как открыта панель.

    Ссылки в сообщениях (оценка визита, лист ожидания, «мои записи») строит
    воркер — заголовков запроса у него нет, а требовать от владельца задать
    `PUBLIC_BASE_URL` руками значит однажды получить салон, где эти ссылки молча
    не работают. Панель открывают по тому же домену, что и страницы для клиента,
    поэтому адрес можно просто запомнить.

    Только https и только не localhost: адрес со стенда разработчика клиенту
    отправить нельзя, а перезаписать им рабочий домен — тем более.
    """
    # Схему берём с оглядкой на реверс-прокси: за Traefik приложение видит http,
    # а клиент — https. Тот же приём, что и у заголовка HSTS в main.py.
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    scheme = forwarded or request.url.scheme
    host = request.headers.get("x-forwarded-host", "").split(",")[0].strip() or request.url.netloc
    origin = f"{scheme}://{host}".rstrip("/")
    if scheme != "https" or host.split(":")[0] in ("localhost", "127.0.0.1", "::1"):
        return
    if tenant.integration.get("publicBaseUrl") == origin:
        return
    tenant.patch_integration({"publicBaseUrl": origin})
    log.info("[%s] публичный адрес сервиса запомнен: %s", tenant.slug, origin)


@router.get("/config", dependencies=[Depends(guard)])
def get_config(request: Request, slug: str = Depends(tenant_slug)) -> dict:
    rt = runtime.for_tenant(slug)
    remember_public_base(rt.tenant, request)
    return {
        "tenant": slug,
        "data": rt.tenant.form_data(),
        "env": rt.tenant.env_preview(),
        "calendarMode": rt.calendar.mode,
        "aiEnabled": rt.agent.available(),
    }


@router.put("/config", dependencies=[Depends(guard)])
def put_config(payload: dict, slug: str = Depends(tenant_slug)) -> dict:
    payload.pop("__env", None)
    tenant = registry.get(slug)
    ok, errors = tenant.save_form(payload)
    if not ok:
        raise HTTPException(422, detail={"ok": False, "errors": errors})
    rt = runtime.reload(slug)  # календарь, БД и агент подхватывают новые настройки
    return {
        "ok": True,
        "tenant": slug,
        "data": rt.tenant.form_data(),
        "env": rt.tenant.env_preview(),
        "calendarMode": rt.calendar.mode,
        "aiEnabled": rt.agent.available(),
    }


@router.post("/validate", dependencies=[Depends(guard)])
def validate(payload: dict) -> dict:
    payload.pop("__env", None)
    errors = validate_config(payload)
    return {"ok": not errors, "errors": errors}


@router.get("/bookings", dependencies=[Depends(guard)])
def bookings(limit: int = Query(default=50, ge=1, le=1000), slug: str = Depends(tenant_slug)) -> dict:
    """Последние записи бизнеса — чтобы администратор видел, что делает бот.

    Отдаём и служебные поля (канал, комментарий, ссылку на событие): карточка
    записи в панели показывает их вместо того, чтобы дёргать API по одной.
    """
    from sqlalchemy import select

    from ..db import Booking, ClientAsset, Conversation

    rt = runtime.for_tenant(slug)
    store = rt.tools.store
    with store.session_factory() as s:
        rows = s.scalars(
            select(Booking).where(Booking.tenant_id == slug)
            .order_by(Booking.created_at.desc()).limit(limit)
        ).all()
        # Канал диалога — единственный честный источник «откуда пришла запись».
        conv_ids = {b.conversation_id for b in rows if b.conversation_id}
        channels = {}
        if conv_ids:
            channels = dict(s.execute(
                select(Conversation.id, Conversation.channel).where(Conversation.id.in_(conv_ids))
            ).all())
        # Визит, оплаченный абонементом, стоит ноль денег — и без названия актива
        # карточка читается как «оплату не сохранили». Поэтому отдаём код и
        # остаток: администратор видит, чем закрыт визит и сколько ещё осталось.
        asset_ids = {b.asset_id for b in rows if b.asset_id}
        assets = {}
        if asset_ids:
            assets = {a.id: a for a in s.scalars(
                select(ClientAsset).where(ClientAsset.id.in_(asset_ids))
            ).all()}

    return {
        "bookings": [
            {
                "id": b.id,
                "masterId": b.master_id,
                "serviceId": b.service_id,
                "master": (rt.tenant.master(b.master_id) or {}).get("name", b.master_id),
                "service": (rt.tenant.service(b.service_id) or {}).get("title", b.service_id),
                # С поясом: без него браузер считает время своим местным, и
                # панель показывала визит на три часа позже — ровно на разницу
                # Монтевидео с UTC.
                "start": utc_iso(b.start_at),
                "end": utc_iso(b.end_at),
                "client": b.client_name,
                "phone": b.phone,
                "comment": b.comment or "",
                "status": b.status,
                "eventId": b.event_id,
                "htmlLink": b.html_link,
                "createdAt": utc_iso(b.created_at),
                "channel": channels.get(b.conversation_id) if b.conversation_id else None,
                "requiresConfirmation": bool(b.requires_confirmation),
                "confirmedByClient": bool(b.confirmed_by_client),
                "notifyConsent": bool(b.notify_consent),
                "clientId": b.client_id,
                "lang": b.lang,
                "source": b.source,
                "promoCode": b.promo_code,
                "priceAmount": b.price_amount,
                "currency": b.currency,
                "paidAmount": b.paid_amount,
                "paymentMethod": b.payment_method,
                "assetId": b.asset_id,
                "assetCode": (assets[b.asset_id].code if b.asset_id in assets else None),
                "assetKind": (assets[b.asset_id].kind if b.asset_id in assets else None),
                # У абонемента остаток — посещения, у сертификата — деньги.
                "assetLeft": (
                    (assets[b.asset_id].remaining_uses
                     if assets[b.asset_id].kind == "membership"
                     else assets[b.asset_id].balance_amount)
                    if b.asset_id in assets else None),
                "discountAmount": b.discount_amount,
                "locationId": b.location_id,
                "groupSize": b.group_size,
            }
            for b in rows
        ]
    }


class ManualBooking(BaseModel):
    masterId: str  # noqa: N815 — контракт с панелью
    serviceId: str  # noqa: N815
    date: str = Field(pattern=DATE_PATTERN)
    time: str = Field(pattern=TIME_PATTERN)
    name: str
    phone: str
    comment: str = ""
    notifyConsent: bool = True  # noqa: N815


class RescheduleBooking(BaseModel):
    masterId: str  # noqa: N815
    date: str = Field(pattern=DATE_PATTERN)
    time: str = Field(pattern=TIME_PATTERN)


@router.post("/bookings", dependencies=[Depends(guard)])
def create_booking(payload: ManualBooking, slug: str = Depends(tenant_slug)) -> dict:
    """Запись, заведённая администратором вручную — например, по телефону.

    Проходит ровно тот же путь, что и виджет: проверка графика, перепроверка
    слота, уникальный индекс, календарь, планирование уведомлений. Отдельной
    «админской» логики записи нет — иначе она разошлась бы с ботом.
    """
    from ..policies import slot_token
    from ..timeutil import zoned
    from ..tools import ToolContext, ToolError

    rt = runtime.for_tenant(slug)
    t = rt.tenant
    if not t.master(payload.masterId) or not t.service(payload.serviceId):
        raise HTTPException(400, "Неизвестная услуга или мастер")

    start = zoned(payload.date, payload.time, t.timezone)
    conv = runtime.store.conversation(None, tenant_id=slug, channel="admin")
    # Подтверждением служит само действие администратора в панели.
    ctx = ToolContext(conversation_id=conv.id, history=[{"role": "user", "content": "да, подтверждаю"}],
                      channel="admin")
    try:
        result = rt.tools.create_booking(
            service_id=payload.serviceId, master_id=payload.masterId, start=start.isoformat(),
            customer_name=payload.name, phone=payload.phone,
            confirmation_token=slot_token(payload.masterId, payload.serviceId, start.isoformat(), slug),
            comment=payload.comment, notify_consent=payload.notifyConsent, ctx=ctx,
        )
    except ToolError as exc:
        raise HTTPException(409 if exc.conflict else 400, exc.message) from exc
    log.info("Администратор создал запись %s", result["booking_id"])
    return {"ok": True, "booking": result}


@router.get("/bookings/{booking_id}/slots", dependencies=[Depends(guard)])
def reschedule_slots(booking_id: str, masterId: str = "",  # noqa: N803 — контракт с панелью
                     date: str = Query(pattern=DATE_PATTERN),
                     slug: str = Depends(tenant_slug)) -> dict:
    """Свободные окна для переноса записи.

    Отдельный эндпоинт, а не публичный ``/api/slots``: там время самой записи
    считается занятым, и панель показывала бы перенос без того окна, в котором
    клиент стоит сейчас. Занятое время сюда не попадает вовсе — администратор
    не должен узнавать о занятости из отказа сервера после сохранения.
    """
    from ..calendar_service import CalendarError
    from ..slots import free_slots

    rt = runtime.for_tenant(slug)
    t = rt.tenant
    booking = rt.tools.store.get_booking(booking_id, tenant_id=slug)
    if not booking:
        raise HTTPException(404, "Запись не найдена")
    master = t.master(masterId or booking.master_id)
    service = t.service(booking.service_id)
    if not master or not service:
        raise HTTPException(400, "Неизвестная услуга или мастер")
    if service["id"] not in (master.get("services") or []):
        raise HTTPException(400, f"{master['name']} не делает «{service['title']}»")
    try:
        slots = free_slots(t, rt.calendar, master, service, date, exclude_booking_id=booking_id)
    except CalendarError as exc:
        log.error("Календарь недоступен: %s", exc)
        raise HTTPException(502, "Не удалось получить расписание из календаря") from exc
    local = booking.start_at.astimezone(tz(t.timezone))
    return {
        "slots": [{"time": s["time"], "start": s["start"].isoformat()} for s in slots],
        "current": {"date": local.date().isoformat(), "time": local.strftime("%H:%M"),
                    "masterId": booking.master_id},
    }


@router.put("/bookings/{booking_id}/reschedule", dependencies=[Depends(guard)])
def reschedule_admin_booking(booking_id: str, payload: RescheduleBooking,
                             slug: str = Depends(tenant_slug)) -> dict:
    from ..policies import slot_token
    from ..timeutil import zoned
    from ..tools import ToolContext, ToolError

    rt = runtime.for_tenant(slug)
    booking = rt.tools.store.get_booking(booking_id, tenant_id=slug)
    if not booking:
        raise HTTPException(404, "Запись не найдена")
    start = zoned(payload.date, payload.time, rt.tenant.timezone)
    ctx = ToolContext(conversation_id=f"admin-{booking_id}", channel="admin",
                      history=[{"role": "user", "content": "да, подтверждаю"}])
    try:
        result = rt.tools.reschedule_booking(
            booking_id=booking_id, master_id=payload.masterId, start=start.isoformat(),
            confirmation_token=slot_token(payload.masterId, booking.service_id, start.isoformat(), slug), ctx=ctx)
    except ToolError as exc:
        raise HTTPException(409 if exc.conflict else 400, exc.message) from exc
    return {"ok": True, "booking": result}


# --- технические перерывы ----------------------------------------------------
# Обед, уборка, доставка. Закрыть время можно было только целым выходным через
# смены — из-за этого обед либо занимали клиентом, либо мастер терял день.

class TimeBlockCreate(BaseModel):
    masterId: str  # noqa: N815
    date: str = Field(pattern=DATE_PATTERN)
    start: str = Field(pattern=TIME_PATTERN)
    end: str = Field(pattern=TIME_PATTERN)
    title: str = Field(default="Перерыв", max_length=120)


def _block_payload(row, tenant) -> dict:
    tz_name = tenant.timezone
    local_start = row.start_at.astimezone(tz(tz_name))
    local_end = row.end_at.astimezone(tz(tz_name))
    return {
        "id": row.id, "masterId": row.master_id, "title": row.title,
        "date": local_start.date().isoformat(),
        "start": local_start.strftime("%H:%M"), "end": local_end.strftime("%H:%M"),
        "inCalendar": bool(row.calendar_event_id),
    }


@router.get("/time-blocks", dependencies=[Depends(guard)])
def list_time_blocks(date_from: str = Query(default="", alias="from", pattern=f"^({DATE_PATTERN})?$"),
                     date_to: str = Query(default="", alias="to", pattern=f"^({DATE_PATTERN})?$"),
                     slug: str = Depends(tenant_slug)) -> dict:
    from ..timeutil import today_key

    rt = runtime.for_tenant(slug)
    tenant = rt.tenant
    start_key = date_from or today_key(tenant.timezone)
    end_key = date_to or start_key
    start = zoned(start_key, "00:00", tenant.timezone)
    end = zoned(end_key, "00:00", tenant.timezone) + timedelta(days=1)
    rows = runtime.store.time_blocks(tenant_id=slug, start=start, end=end)
    return {"blocks": [_block_payload(row, tenant) for row in rows]}


@router.post("/time-blocks", dependencies=[Depends(guard)])
def create_time_block(payload: TimeBlockCreate, slug: str = Depends(tenant_slug)) -> dict:
    """Перерыв в расписании мастера. Занимает время так же, как запись."""
    rt = runtime.for_tenant(slug)
    tenant = rt.tenant
    master = tenant.master(payload.masterId)
    if not master:
        raise HTTPException(404, "Мастера нет")
    if payload.start >= payload.end:
        raise HTTPException(400, "Конец перерыва должен быть позже начала")

    start = zoned(payload.date, payload.start, tenant.timezone)
    end = zoned(payload.date, payload.end, tenant.timezone)
    # Поверх записи перерыв не ставим: клиент уже придёт, и «обед» на этом месте
    # означал бы, что кто-то один останется в дверях.
    clash = runtime.store.overlapping(payload.masterId, start, end, tenant_id=slug)
    if clash:
        raise HTTPException(409, detail={"error": "На это время уже есть запись",
                                         "bookings": len(clash)})

    row = runtime.store.add_time_block(tenant_id=slug, master_id=payload.masterId,
                                       start_at=start, end_at=end, title=payload.title)
    # Сначала база, потом календарь: перерыв нужен мастеру сейчас, а календарь
    # может быть недоступен. Отказ показываем явно, а не откатываем молча.
    warning = ""
    try:
        event = rt.calendar.create_block(master=master, title=row.title, start=start, end=end)
        runtime.store.attach_block_event(row.id, event["id"])
        row.calendar_event_id = event["id"]
    except CalendarError as exc:
        log.error("[%s] перерыв %s не попал в календарь: %s", slug, row.id, exc)
        warning = "Перерыв сохранён, но в календарь мастера не попал — проверьте подключение Google"
    return {"ok": True, "block": _block_payload(row, tenant), "warning": warning}


@router.delete("/time-blocks/{block_id}", dependencies=[Depends(guard)])
def delete_time_block(block_id: str, slug: str = Depends(tenant_slug)) -> dict:
    """Снимает перерыв и убирает его событие из календаря мастера."""
    rt = runtime.for_tenant(slug)
    row = runtime.store.get_time_block(block_id, tenant_id=slug)
    if not row:
        raise HTTPException(404, "Перерыв не найден")

    master = rt.tenant.master(row.master_id)
    warning = ""
    if row.calendar_event_id and master:
        try:
            rt.calendar.delete_event(master, row.calendar_event_id)
        except CalendarError as exc:
            # Иначе в календаре мастера останется висеть призрак обеда.
            log.error("[%s] событие перерыва %s не снялось: %s", slug, block_id, exc)
            warning = "Перерыв снят, но событие в календаре мастера осталось — удалите его вручную"
    runtime.store.drop_time_block(block_id, tenant_id=slug)
    return {"ok": True, "warning": warning}


# --- календарь смен ----------------------------------------------------------
# Правила графика живут в `shifts.py`: тем же занят кабинет мастера, а две копии
# проверок разошлись бы на первой же правке.


class ShiftUpdate(BaseModel):
    date: str = Field(pattern=DATE_PATTERN)
    # default — как в недельной сетке, off — выходной, work — работает
    # (пустые часы означают «в обычные часы», заполненные — свою смену).
    mode: str = Field(pattern="^(default|off|work)$")
    start: str = ""
    end: str = ""
    # Выходной поверх занятого дня подтверждается отдельно: записи при этом
    # никуда не деваются, и мастер должен видеть, что именно он закрывает.
    force: bool = False


@router.get("/masters/{master_id}/shifts", dependencies=[Depends(guard)])
def get_master_shifts(master_id: str, month: str = Query(default="", pattern=f"^({MONTH_PATTERN})?$"),
                      slug: str = Depends(tenant_slug)) -> dict:
    """Месяц графика одного мастера: что даёт недельная сетка и чем её правили."""
    try:
        return calendar_for(slug, master_id, month)
    except ShiftError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


@router.put("/masters/{master_id}/shifts", dependencies=[Depends(guard)])
def put_master_shift(master_id: str, payload: ShiftUpdate,
                     slug: str = Depends(tenant_slug)) -> dict:
    """Один день графика. Возвращает пересчитанный месяц — панель не гадает."""
    try:
        return set_shift(slug, master_id, date=payload.date, mode=payload.mode,
                         start=payload.start, end=payload.end, force=payload.force)
    except ShiftError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


# --- кабинет мастера ---------------------------------------------------------
# Мастеру не нужна панель: там выручка салона, клиентская база и ключи. Ему нужен
# свой день и свой график. Доступ туда — личная ссылка: владелец выдаёт её из
# панели, отправляет мастеру и отзывает, когда тот уходит.


def team_base_url(slug: str) -> str:
    """Адрес кабинета. Поддомен задаётся `TEAM_BASE_URL`; без него ссылка ведёт
    на `/team` рабочего домена — работает сразу, ещё до настройки DNS."""
    import os

    from ..notify.service import public_base_url

    named = (os.getenv("TEAM_BASE_URL") or "").strip().rstrip("/")
    if named:
        return named
    base = public_base_url(runtime.for_tenant(slug).tenant)
    return f"{base}/team" if base else "/team"


@router.get("/masters/access", dependencies=[Depends(guard)])
def masters_access(slug: str = Depends(tenant_slug)) -> dict:
    """У кого есть доступ в кабинет и когда он туда заходил. Самих ссылок здесь
    нет: ключ существует только в момент выдачи, дальше — лишь его хеш."""
    tenant = runtime.for_tenant(slug).tenant
    return {
        "base": team_base_url(slug),
        "masters": [
            {"id": m["id"], "name": m.get("name") or m["id"],
             **staff.key_status(runtime.store, slug, m["id"])}
            for m in tenant.salon.get("masters", [])
        ],
    }


@router.post("/masters/{master_id}/access", dependencies=[Depends(guard)])
def issue_master_access(master_id: str, slug: str = Depends(tenant_slug)) -> dict:
    """Выдаёт мастеру личную ссылку. Прежняя перестаёт работать сразу.

    ПИН владелец не задаёт и не узнаёт: мастер придумает его сам, открыв ссылку
    впервые. Владельцу остаётся отправить ссылку — диктовать и хранить цифры
    не нужно, а забытый ПИН чинится кнопкой «Сбросить ПИН».

    Ключ уходит в ответ ровно один раз — показать его повторно неоткуда: в базе
    только хеш.
    """
    tenant = runtime.for_tenant(slug).tenant
    if not tenant.master(master_id):
        raise HTTPException(404, "Мастера нет")
    key = staff.issue_key(runtime.store, slug, master_id)
    # Ключ в якоре адреса: на сервер он не уходит вовсе, значит не осядет ни в
    # логах прокси, ни в истории переходов.
    return {"ok": True, "link": f"{team_base_url(slug)}#k={key}"}


@router.post("/masters/{master_id}/access/pin", dependencies=[Depends(guard)])
def reset_master_pin(master_id: str, slug: str = Depends(tenant_slug)) -> dict:
    """Мастер забыл ПИН — сбрасываем, ссылка остаётся прежней.

    Отдельная кнопка, а не «выдать заново»: рассылать новую ссылку из-за
    забытых четырёх цифр значит каждый раз объяснять, почему старая перестала
    открываться.
    """
    if not runtime.for_tenant(slug).tenant.master(master_id):
        raise HTTPException(404, "Мастера нет")
    return {"ok": True, "reset": staff.reset_pin(runtime.store, slug, master_id)}


@router.delete("/masters/{master_id}/access", dependencies=[Depends(guard)])
def revoke_master_access(master_id: str, slug: str = Depends(tenant_slug)) -> dict:
    """Отзыв доступа: ссылка и все открытые по ней кабинеты закрываются."""
    return {"ok": True, "revoked": staff.revoke_key(runtime.store, slug, master_id)}


# --- хранилище данных --------------------------------------------------------

@router.get("/database/status", dependencies=[Depends(owner_only)])
def database_status(slug: str = Depends(tenant_slug)) -> dict:
    """Паспорт базы, под которой реально работает сервис.

    Форма выбора хранилища здесь была фикцией: база одна на весь сервис, её
    адрес приходит из ``DATABASE_URL``, и настроить доступ к базе через форму,
    которая сама хранится в этой базе, невозможно. Поэтому раздел показывает
    факты, а не поля ввода.
    """
    info = runtime.store.describe(tenant_id=slug)
    info["tenant"] = slug
    return info


@router.post("/database/check", dependencies=[Depends(owner_only)])
def database_check() -> dict:
    """Круговая проверка записи и чтения — по кнопке «Проверить связь»."""
    return runtime.store.selftest()


# --- подключение Google Calendar --------------------------------------------

def _redirect_uri(request: Request) -> str:
    """Тот же URL нужно добавить в Google Cloud Console → Authorized redirect URIs."""
    return str(request.base_url).rstrip("/") + "/api/admin/google/callback"


@router.get("/google/status", dependencies=[Depends(owner_only)])
def google_status(request: Request, slug: str = Depends(tenant_slug)) -> dict:
    tenant = registry.get(slug)
    integration = tenant.google
    rt = runtime.for_tenant(slug)
    connected = bool(integration.get("refreshToken")) and integration.get("mode") == "oauth"
    has_client = bool(integration.get("clientId")) and bool(integration.get("clientSecret"))
    return {
        "connected": connected,
        "account": integration.get("googleAccount", ""),
        "hasClientCredentials": has_client,
        "redirectUri": _redirect_uri(request),
        "mode": integration.get("mode", "local"),
        # Настроено, но не работает — это не то же самое, что «не подключали».
        "degraded": bool(rt.calendar.degraded),
        "error": rt.calendar.error,
        "calendarMode": rt.calendar.mode,
    }


class GoogleCredentials(BaseModel):
    clientId: str  # noqa: N815 — контракт с формой
    clientSecret: str  # noqa: N815


@router.post("/google/credentials", dependencies=[Depends(owner_only)])
def google_credentials(payload: GoogleCredentials, slug: str = Depends(tenant_slug)) -> dict:
    """Client ID и Secret из Google Cloud Console — в обход формы.

    Через форму они не сохранялись: сохранение проверяет конфигурацию целиком, а
    незаконченное подключение Google считалось ошибкой — креды не доживали до
    кнопки входа, ради которой вводились.
    """
    client_id = payload.clientId.strip()
    client_secret = payload.clientSecret.strip()
    if not client_id or not client_secret:
        raise HTTPException(422, "Нужны и Client ID, и Client Secret")

    registry.get(slug).patch_integration({"clientId": client_id, "clientSecret": client_secret})
    runtime.reload(slug)
    return {"ok": True}


@router.post("/google/verify", dependencies=[Depends(owner_only)])
def google_verify(slug: str = Depends(tenant_slug)) -> dict:
    """Настоящая проверка: создаём в календаре мастера событие и тут же удаляем.

    Зелёная галочка «подключено» ничего не доказывает: доступ мог быть выдан,
    а календарь мастера — не расшарен. Круговой тест ловит именно это, причём
    до того, как на нём споткнётся первый живой клиент.
    """
    from datetime import datetime, timedelta, timezone as tz

    from ..calendar_service import CalendarError, calendar_id

    rt = runtime.for_tenant(slug)
    if rt.calendar.mode != "google":
        raise HTTPException(409, rt.calendar.error or "Google Calendar не подключён")

    # Далеко в будущем и на минуту: даже если удаление не сработает, событие
    # не попадёт в рабочее расписание салона.
    start = datetime.now(tz.utc) + timedelta(days=3650)
    probe_service = {"id": "__probe", "title": "Проверка связи", "duration": 1}
    results = []
    for master in rt.tenant.masters:
        entry = {"masterId": master["id"], "master": master.get("name", master["id"]),
                 "calendarId": calendar_id(master)}
        try:
            event = rt.calendar.create_event(
                master=master, service=probe_service, start=start, end=start + timedelta(minutes=1),
                client_name="Demo Salon", phone="", comment="Проверка подключения из панели.",
            )
            rt.calendar.delete_event(master, event["id"])
            entry.update(ok=True, detail="событие создано и удалено")
        except CalendarError as exc:
            entry.update(ok=False, detail=_google_hint(str(exc)))
        results.append(entry)

    ok = all(r["ok"] for r in results) and bool(results)
    log.info("Проверка Google Calendar для %s: %s", slug, "успешно" if ok else "с ошибками")
    return {"ok": ok, "account": rt.tenant.google.get("googleAccount", ""), "masters": results}


def _google_hint(message: str) -> str:
    """Ошибки Google приходят англоязычным JSON — переводим в понятное действие."""
    text = message.lower()
    if "notfound" in text or "404" in text:
        return "Календарь не найден: проверьте ID календаря у мастера."
    if "forbidden" in text or "403" in text or "writer" in text:
        return ("Нет прав на запись. Откройте календарь мастера → «Настройки и общий доступ» → "
                "предоставьте доступ подключённому аккаунту с правом «Внесение изменений в мероприятия».")
    if "invalid_grant" in text or "401" in text:
        return "Доступ отозван или истёк — подключите Google заново."
    return message[:300]


@router.get("/google/start", dependencies=[Depends(owner_only)])
def google_start(request: Request, slug: str = Depends(tenant_slug)) -> RedirectResponse:
    """Уводим владельца салона на экран согласия Google."""
    tenant = registry.get(slug)
    try:
        url = google_oauth.build_auth_url(tenant, _redirect_uri(request))
    except google_oauth.OAuthError as exc:
        raise HTTPException(422, str(exc)) from exc
    return RedirectResponse(url, status_code=302)


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = "") -> HTMLResponse:
    """Google возвращает сюда. Токен сохраняем в конфигурации бизнеса."""
    if error:
        return _callback_page(False, f"Google отказал: {error}", "")
    try:
        pending = google_oauth.consume_state(state)
        tenant = registry.get(pending.tenant)
        result = google_oauth.exchange_code(tenant, code, pending.redirect_uri)
    except (google_oauth.OAuthError, TenantError) as exc:
        return _callback_page(False, str(exc), "")

    tenant.patch_integration({
        "mode": "oauth",
        "refreshToken": result["refresh_token"],
        "googleAccount": result["email"],
    })
    runtime.reload(tenant.slug)
    log.info("Бизнес %s подключил Google (%s)", tenant.slug, result["email"] or "аккаунт")
    return _callback_page(True, result["email"], tenant.slug)


def _callback_page(ok: bool, message: str, slug: str) -> HTMLResponse:
    title = "Google подключён" if ok else "Не удалось подключить"
    detail = (f"Аккаунт: {message}" if ok and message else
              "Доступ выдан." if ok else message)
    back = f"/admin.html?tenant={slug}" if slug else "/admin.html"
    return HTMLResponse(f"""<!doctype html><meta charset="utf-8">
<title>{title}</title>
<style>
 body {{ font-family: 'DM Sans', system-ui, sans-serif; background:#F5EFE6; color:#292521;
        display:grid; place-items:center; height:100vh; margin:0; text-align:center; padding:24px; }}
 .box {{ background:#FFFDF8; border:1px solid rgba(41,37,33,.1); border-radius:18px;
         padding:34px 40px; max-width:460px; box-shadow:0 20px 50px rgba(41,37,33,.12); }}
 h1 {{ font-family:'Cormorant Garamond',Georgia,serif; font-weight:400; font-size:28px; margin:0 0 10px; }}
 p {{ color:#8A7A6C; line-height:1.6; margin:0 0 22px; font-size:14px; }}
 a {{ background:#D97855; color:#fff; text-decoration:none; padding:11px 22px; border-radius:999px;
      display:inline-block; font-size:14px; }}
 .bad h1 {{ color:#A8321A; }}
</style>
<div class="box {'ok' if ok else 'bad'}">
  <h1>{title}</h1><p>{detail}</p>
  <a href="{back}">Вернуться в настройки</a>
</div>
<script>if (window.opener) {{ window.opener.postMessage({{google:{str(ok).lower()}}}, '*'); setTimeout(() => window.close(), 1200); }}</script>""")


@router.get("/google/calendars", dependencies=[Depends(owner_only)])
def google_calendars(slug: str = Depends(tenant_slug)) -> dict:
    """Список календарей аккаунта — мастер выбирает свой, а не вводит ID руками."""
    tenant = registry.get(slug)
    try:
        return {"calendars": google_oauth.list_calendars(tenant)}
    except google_oauth.OAuthError as exc:
        raise HTTPException(422, str(exc)) from exc


class MasterCalendar(BaseModel):
    # Название можно задать своё: в аккаунте, где уже двадцать календарей,
    # «Мастер» без салона ничего не значит.
    title: str = ""


@router.post("/masters/{master_id}/calendar", dependencies=[Depends(owner_only)])
def create_master_calendar(master_id: str, payload: MasterCalendar,
                           slug: str = Depends(tenant_slug)) -> dict:
    """Отдельный Google-календарь мастеру — и сразу привязать его к карточке.

    Новый мастер заводится с ``calendarId: "primary"``, то есть на основном
    календаре аккаунта. Пока салон в локальном режиме это незаметно: занятость
    считается по своей базе, по коду мастера. После подключения Google двое на
    «primary» начинают отнимать окна друг у друга — эта кнопка и существует,
    чтобы такого не случилось.
    """
    tenant = registry.get(slug)
    master = tenant.master(master_id)
    if not master:
        raise HTTPException(404, "Мастера нет")
    if tenant.integration.get("mode", "local") == "local":
        raise HTTPException(400, "Сначала подключите Google — вкладка «Каналы связи»")

    title = payload.title.strip() or f"{tenant.title} — {master['name']}"
    try:
        created = google_oauth.create_calendar(
            tenant, title,
            f"Записи мастера {master['name']}. Календарь ведёт бот записи, "
            f"события создаются автоматически.")
    except google_oauth.OAuthError as exc:
        raise HTTPException(422, str(exc)) from exc

    tenant.patch_master(master_id, {"calendarId": created["id"]})
    runtime.reload(slug)   # календарь мастера читает уже новый ID
    log.info("[%s] мастеру %s создан календарь %s", slug, master_id, created["id"])
    return {"ok": True, "calendarId": created["id"], "title": created["title"],
            "calendars": google_oauth.list_calendars(tenant)}


@router.post("/google/disconnect", dependencies=[Depends(owner_only)])
def google_disconnect(slug: str = Depends(tenant_slug)) -> dict:
    tenant = registry.get(slug)
    tenant.patch_integration({"mode": "local", "refreshToken": "", "googleAccount": ""})
    runtime.reload(slug)
    return {"ok": True}


# --- подключение Telegram ----------------------------------------------------

class TelegramToken(BaseModel):
    token: str


@router.get("/telegram/status", dependencies=[Depends(owner_only)])
def telegram_status(slug: str = Depends(tenant_slug)) -> dict:
    """Состояние бота владельца: живой ли токен и куда уходят уведомления."""
    handoff = registry.get(slug).handoff
    token = (handoff.get("telegramBotToken") or "").strip()
    chat_id = str(handoff.get("telegramChatId") or "").strip()
    if not token:
        return {"hasToken": False, "connected": False, "chatId": "", "bot": "", "error": ""}

    try:
        bot = telegram.me(token)
    except telegram.TelegramError as exc:
        # Токен есть, но отозван — это не то же самое, что «не подключали».
        return {"hasToken": True, "connected": False, "chatId": chat_id, "bot": "",
                "error": str(exc), "degraded": True}
    return {"hasToken": True, "connected": bool(chat_id), "chatId": chat_id,
            "bot": bot["username"], "botTitle": bot["title"], "error": "",
            "link": f"https://t.me/{bot['username']}" if bot["username"] else ""}


def _wire_webhook(slug: str, token: str, request: Request) -> None:
    """Подписывает бота на входящие. Молча: без вебхука он всё равно шлёт записи.

    Локальная разработка сюда не годится — Telegram не достучится до
    `127.0.0.1`, поэтому на http-адресе вебхук даже не пробуем.
    """
    base = str(request.base_url).rstrip("/")
    if not base.startswith("https://"):
        log.info("[%s] вебхук Telegram пропущен: нужен https-адрес", slug)
        return
    try:
        telegram.set_webhook(token, f"{base}/api/telegram/{slug}/webhook", webhook_secret(slug))
        log.info("[%s] вебхук Telegram установлен", slug)
    except telegram.TelegramError as exc:
        log.error("[%s] вебхук Telegram не установлен: %s", slug, exc)


@router.post("/telegram/connect", dependencies=[Depends(owner_only)])
def telegram_connect(payload: TelegramToken, request: Request,
                     slug: str = Depends(tenant_slug)) -> dict:
    """Токен от @BotFather: проверяем и сохраняем сами — форму заполнять не нужно."""
    token = payload.token.strip()
    try:
        bot = telegram.me(token)
    except telegram.TelegramError as exc:
        raise HTTPException(422, str(exc)) from exc

    tenant = registry.get(slug)
    tenant.patch_integration({"handoff.telegramBotToken": token})
    runtime.reload(slug)
    _wire_webhook(slug, token, request)
    log.info("[%s] подключён Telegram-бот @%s", slug, bot["username"])
    return {"ok": True, "bot": bot["username"], "botTitle": bot["title"],
            "link": f"https://t.me/{bot['username']}" if bot["username"] else ""}


@router.post("/telegram/link", dependencies=[Depends(owner_only)])
def telegram_link(slug: str = Depends(tenant_slug)) -> dict:
    """Ищет чат, из которого боту написали, и запоминает его.

    ``chatId`` — самое неудобное поле панели: это число, которое владелец обычно
    ищет через сторонних ботов. Вместо этого он пишет своему боту «/start», а
    номер чата сервис берёт из истории сам.

    Сначала спрашиваем вебхук: при активной подписке «/start» достаётся ему, и
    в `getUpdates` этого сообщения уже не будет — Telegram доставленное второй
    раз не отдаёт. `getUpdates` остаётся для случая, когда вебхука нет вовсе.
    """
    tenant = registry.get(slug)
    token = (tenant.handoff.get("telegramBotToken") or "").strip()
    chat = telegram_bot.pending_chat(runtime.store, slug)
    if not chat:
        try:
            with telegram.webhook_paused(token, secret=webhook_secret(slug)):
                chat = telegram.find_chat(token)
        except telegram.TelegramError as exc:
            raise HTTPException(422, str(exc)) from exc
    if not chat:
        raise HTTPException(422, "Боту ещё никто не писал — откройте чат и отправьте «/start»")
    telegram_bot.forget_start(runtime.store, slug)

    # Уведомления владельцу теперь есть куда слать — переключаем канал сами.
    tenant.patch_integration({
        "handoff.telegramChatId": chat["id"],
        "notifications.ownerProvider": "telegram",
    })
    runtime.reload(slug)
    log.info("[%s] Telegram: уведомления уходят в чат %s", slug, chat["title"] or chat["id"])
    return {"ok": True, "chatId": chat["id"], "chatTitle": chat["title"], "chatType": chat["type"]}


@router.post("/telegram/test", dependencies=[Depends(owner_only)])
def telegram_test(slug: str = Depends(tenant_slug)) -> dict:
    """Настоящее сообщение в чат: «подключено» само по себе ничего не доказывает."""
    tenant = registry.get(slug)
    handoff = tenant.handoff
    token = (handoff.get("telegramBotToken") or "").strip()
    chat_id = str(handoff.get("telegramChatId") or "").strip()
    if not chat_id:
        raise HTTPException(422, "Чат не привязан — нажмите «Связать чат»")
    # Название берём из настроек бизнеса: сервис обслуживает много салонов, и
    # владельцу «Second Demo» приходило сообщение, подписанное «Demo Salon».
    title = tenant.salon.get("name") or slug
    try:
        telegram.send(token, chat_id, f"{title}: проверка связи. Сюда будут приходить "
                                      f"уведомления салона «{title}».")
    except telegram.TelegramError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True}


@router.get("/telegram/masters", dependencies=[Depends(guard)])
def telegram_masters(slug: str = Depends(tenant_slug)) -> dict:
    """Кто из мастеров подключён и по какой ссылке подключить остальных."""
    tenant = registry.get(slug)
    token = (tenant.handoff.get("telegramBotToken") or "").strip()
    bot = ""
    if token:
        try:
            bot = telegram.me(token)["username"]
        except telegram.TelegramError:
            bot = ""  # состояние бота показывает свой эндпоинт, здесь это не ошибка

    masters = []
    for master in tenant.masters:
        code = master_link_code(slug, master["id"])
        masters.append({
            "id": master["id"], "name": master.get("name") or master["id"],
            "chatId": str(master.get("telegramChatId") or ""),
            "connected": bool(str(master.get("telegramChatId") or "").strip()),
            "link": f"https://t.me/{bot}?start={code}" if bot else "",
        })
    return {"botConnected": bool(bot), "bot": bot, "masters": masters}


@router.post("/telegram/masters/{master_id}/link", dependencies=[Depends(guard)])
def telegram_master_link(master_id: str, slug: str = Depends(tenant_slug)) -> dict:
    """Ищет чат, из которого мастер открыл свою ссылку, и запоминает его.

    Различает мастеров по коду в ссылке, а не по «кто написал последним»: двое
    нажали «Начать» подряд — и обоим уходили бы чужие записи.
    """
    tenant = registry.get(slug)
    master = tenant.master(master_id)
    if not master:
        raise HTTPException(404, f"Нет мастера с кодом «{master_id}»")

    # Нажатие «Начать» вебхук привязывает сам — тогда кнопке остаётся подтвердить.
    bound = str(master.get("telegramChatId") or "").strip()
    if bound:
        return {"ok": True, "master": master_id, "chatId": bound, "chatTitle": ""}

    token = (tenant.handoff.get("telegramBotToken") or "").strip()
    try:
        with telegram.webhook_paused(token, secret=webhook_secret(slug)):
            chat = telegram.find_chat_by_code(token, master_link_code(slug, master_id))
    except telegram.TelegramError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not chat:
        raise HTTPException(422, f"{master.get('name') or master_id} ещё не открыл ссылку — "
                                 "отправьте её и попросите нажать «Начать»")

    masters = [dict(m) for m in tenant.salon.get("masters") or []]
    for m in masters:
        if m.get("id") == master_id:
            m["telegramChatId"] = chat["id"]
    tenant.patch_salon({"masters": masters})
    runtime.reload(slug)
    log.info("[%s] Telegram: записи мастера %s уходят в чат %s", slug, master_id, chat["id"])
    return {"ok": True, "master": master_id, "chatId": chat["id"], "chatTitle": chat["title"]}


@router.post("/telegram/masters/{master_id}/test", dependencies=[Depends(guard)])
def telegram_master_test(master_id: str, slug: str = Depends(tenant_slug)) -> dict:
    """Настоящее сообщение мастеру: «привязано» само по себе ничего не доказывает."""
    tenant = registry.get(slug)
    master = tenant.master(master_id)
    if not master:
        raise HTTPException(404, f"Нет мастера с кодом «{master_id}»")
    chat_id = str(master.get("telegramChatId") or "").strip()
    if not chat_id:
        raise HTTPException(422, "Чат мастера не привязан")
    token = (tenant.handoff.get("telegramBotToken") or "").strip()
    title = tenant.salon.get("name") or slug
    try:
        telegram.send(token, chat_id, f"{title}: проверка связи. Сюда будут приходить "
                                      f"записи мастера {master.get('name') or master_id}.")
    except telegram.TelegramError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True}


@router.post("/telegram/masters/{master_id}/unlink", dependencies=[Depends(guard)])
def telegram_master_unlink(master_id: str, slug: str = Depends(tenant_slug)) -> dict:
    tenant = registry.get(slug)
    masters = [dict(m) for m in tenant.salon.get("masters") or []]
    for m in masters:
        if m.get("id") == master_id:
            m["telegramChatId"] = ""
    tenant.patch_salon({"masters": masters})
    runtime.reload(slug)
    return {"ok": True}


@router.post("/telegram/disconnect", dependencies=[Depends(owner_only)])
def telegram_disconnect(slug: str = Depends(tenant_slug)) -> dict:
    tenant = registry.get(slug)
    patch: dict = {"handoff.telegramBotToken": "", "handoff.telegramChatId": ""}
    # Канал владельца без бота работать не будет — возвращаем в лог, а не молчим.
    if (tenant.integration.get("notifications") or {}).get("ownerProvider") == "telegram":
        patch["notifications.ownerProvider"] = "console"
    tenant.patch_integration(patch)
    runtime.reload(slug)
    return {"ok": True}


# --- подключение AI ----------------------------------------------------------

# --- подключение Twilio ------------------------------------------------------

class TwilioCredentials(BaseModel):
    accountSid: str  # noqa: N815 — контракт с формой
    authToken: str   # noqa: N815


def _twilio_keys(slug: str) -> tuple[str, str]:
    tenant = registry.get(slug)
    n = tenant.notifications
    return (n.get("twilioAccountSid") or "").strip(), (n.get("twilioAuthToken") or "").strip()


@router.get("/twilio/status", dependencies=[Depends(owner_only)])
def twilio_status(slug: str = Depends(tenant_slug)) -> dict:
    """Подключён ли аккаунт, чей он и какие у него номера."""
    tenant = registry.get(slug)
    sid, token = _twilio_keys(slug)
    n = tenant.notifications
    base = {
        "hasKeys": bool(sid and token),
        "whatsappFrom": n.get("twilioWhatsappFrom") or "",
        "smsFrom": n.get("twilioSmsFrom") or "",
        "provider": n.get("provider") or "console",
        "sandbox": twilio_api.SANDBOX_WHATSAPP,
    }
    if not (sid and token):
        return {**base, "connected": False, "account": "", "numbers": []}
    try:
        info = twilio_api.account(sid, token)
    except twilio_api.TwilioError as exc:
        # Ключи есть, но не работают — это не «не подключали», и молчать нельзя.
        return {**base, "connected": False, "degraded": True, "error": str(exc),
                "account": "", "numbers": []}
    try:
        found = twilio_api.numbers(sid, token)
    except twilio_api.TwilioError:
        found = []   # номера — удобство выбора, не критичный путь
    return {**base, "connected": True, "account": info["name"], "accountType": info["type"],
            "numbers": found}


@router.post("/twilio/connect", dependencies=[Depends(owner_only)])
def twilio_connect(payload: TwilioCredentials, slug: str = Depends(tenant_slug)) -> dict:
    """Ключи проверяются до сохранения — нерабочие в настройки не попадут."""
    sid, token = payload.accountSid.strip(), payload.authToken.strip()
    try:
        info = twilio_api.account(sid, token)
        found = twilio_api.numbers(sid, token)
    except twilio_api.TwilioError as exc:
        raise HTTPException(422, str(exc)) from exc

    tenant = registry.get(slug)
    patch = {"notifications.twilioAccountSid": sid, "notifications.twilioAuthToken": token}
    # Единственный SMS-номер выбирать не за что — проставляем сами.
    sms = [n["number"] for n in found if n["sms"]]
    if len(sms) == 1 and not (tenant.notifications.get("twilioSmsFrom") or "").strip():
        patch["notifications.twilioSmsFrom"] = sms[0]
    tenant.patch_integration(patch)
    runtime.reload(slug)
    log.info("[%s] подключён Twilio: %s", slug, info["name"])
    return {"ok": True, "account": info["name"], "numbers": found}


class TwilioSenders(BaseModel):
    whatsappFrom: str = ""  # noqa: N815
    smsFrom: str = ""       # noqa: N815
    useTwilio: bool = True  # noqa: N815 — сразу переключить канал клиента


@router.post("/twilio/senders", dependencies=[Depends(owner_only)])
def twilio_senders(payload: TwilioSenders, slug: str = Depends(tenant_slug)) -> dict:
    """Отправители и переключение канала — без похода в форму."""
    tenant = registry.get(slug)
    patch = {
        "notifications.twilioWhatsappFrom": payload.whatsappFrom.strip(),
        "notifications.twilioSmsFrom": payload.smsFrom.strip(),
    }
    if payload.useTwilio:
        patch["notifications.provider"] = "twilio"
        patch["notifications.enabled"] = True
    tenant.patch_integration(patch)
    runtime.reload(slug)
    return {"ok": True}


class TwilioTest(BaseModel):
    to: str


@router.post("/twilio/test", dependencies=[Depends(owner_only)])
def twilio_test(payload: TwilioTest, slug: str = Depends(tenant_slug)) -> dict:
    """Настоящее сообщение на указанный номер — «подключено» ничего не доказывает."""
    from ..notify import providers

    tenant = registry.get(slug)
    n = tenant.notifications
    sid, token = _twilio_keys(slug)
    if not (sid and token):
        raise HTTPException(422, "Сначала подключите Twilio")
    channel = "whatsapp" if (n.get("clientChannel") or "whatsapp") == "whatsapp" else "sms"
    cfg = {"accountSid": sid, "authToken": token,
           "whatsappFrom": n.get("twilioWhatsappFrom"), "smsFrom": n.get("twilioSmsFrom"),
           "contentSids": {}}
    try:
        result = providers.send(
            provider="twilio", channel=channel, to=payload.to,
            body=f"{tenant.salon.get('name') or slug}: проверка связи. "
                 f"Сюда будут приходить подтверждения и напоминания о записи.",
            template_name="test", cfg=cfg,
        )
    except providers.SendError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "channel": channel, "messageId": result.provider_message_id}


@router.post("/twilio/disconnect", dependencies=[Depends(owner_only)])
def twilio_disconnect(slug: str = Depends(tenant_slug)) -> dict:
    tenant = registry.get(slug)
    patch = {"notifications.twilioAccountSid": "", "notifications.twilioAuthToken": ""}
    # Без ключей twilio-провайдер молчит — возвращаем в лог, а не притворяемся.
    if (tenant.integration.get("notifications") or {}).get("provider") == "twilio":
        patch["notifications.provider"] = "console"
    tenant.patch_integration(patch)
    runtime.reload(slug)
    return {"ok": True}


class AiConnect(BaseModel):
    provider: str
    apiKey: str = ""  # noqa: N815 — контракт с формой
    model: str = ""


@router.get("/ai/status", dependencies=[Depends(owner_only)])
def ai_status(slug: str = Depends(tenant_slug)) -> dict:
    """Что подключено и какие провайдеры вообще есть — для карточек в панели."""
    ai = registry.get(slug).ai
    enabled, has_key = bool(ai.get("enabled")), bool(ai.get("apiKey"))
    return {
        "enabled": enabled,
        "provider": ai.get("provider") or "",
        "model": ai.get("model") or "",
        "hasKey": has_key,
        # «Включено, но ключа нет» — отдельное состояние, а не «выключено»:
        # так бывает после переезда, когда ключ остался в старом окружении.
        # Бот при этом жив и ведёт кнопочный сценарий, но владелец ждёт диалога.
        "degraded": enabled and not has_key,
        "providers": ai_providers.catalog(),
    }


@router.post("/ai/connect", dependencies=[Depends(owner_only)])
def ai_connect(payload: AiConnect, slug: str = Depends(tenant_slug)) -> dict:
    """Ключ проверяется до сохранения — нерабочий в настройки не попадёт.

    Заодно сверяем модель со списком у провайдера: «ключ верный, но модель не
    та» даёт молчащего бота, и разбираться в этом на живом клиенте дороже.
    """
    try:
        cfg = ai_providers.get(payload.provider)
        models = ai_providers.verify(payload.provider, payload.apiKey.strip())
    except ai_providers.ProviderError as exc:
        raise HTTPException(422, str(exc)) from exc

    model = payload.model.strip() or cfg["defaultModel"]
    if models and model not in models:
        # Список у бесплатных провайдеров живёт своей жизнью — подставляем
        # ближайшую модель того же семейства, а не падаем.
        fallback = next((m for m in models if m.startswith(model.split("-")[0])), "")
        if not fallback:
            raise HTTPException(422, f"У ключа нет доступа к модели «{model}». "
                                     f"Доступны, например: {', '.join(models[:5])}")
        model = fallback

    tenant = registry.get(slug)
    tenant.patch_integration({
        "ai.enabled": True, "ai.provider": payload.provider, "ai.model": model,
        "ai.apiKey": payload.apiKey.strip(),
    })
    runtime.reload(slug)
    log.info("[%s] AI-диалог подключён: %s / %s", slug, payload.provider, model)
    return {"ok": True, "provider": payload.provider, "model": model}


@router.post("/ai/test", dependencies=[Depends(owner_only)])
def ai_test(slug: str = Depends(tenant_slug)) -> dict:
    """Живой запрос к модели по кнопке «Проверить»."""
    ai = registry.get(slug).ai
    if not ai.get("apiKey"):
        raise HTTPException(422, "Ключ не сохранён — подключите провайдера")
    try:
        answer = ai_providers.probe(ai.get("provider") or "openai", ai["apiKey"], ai.get("model") or "")
    except ai_providers.ProviderError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "answer": answer[:200]}


@router.post("/ai/disconnect", dependencies=[Depends(owner_only)])
def ai_disconnect(slug: str = Depends(tenant_slug)) -> dict:
    tenant = registry.get(slug)
    tenant.patch_integration({"ai.enabled": False, "ai.apiKey": ""})
    runtime.reload(slug)
    return {"ok": True}


@router.get("/embed", dependencies=[Depends(guard)])
def embed(slug: str = Depends(tenant_slug), origin: str = Query(default="")) -> dict:
    """Готовый код вставки виджета для этого бизнеса."""
    base = (origin or "https://ваш-домен").rstrip("/")
    return {
        "tenant": slug,
        "snippet": f'<script src="{base}/widget.js" data-api="{base}" data-tenant="{slug}"></script>',
        "demo": f"{base}/demo.html?tenant={slug}",
    }
