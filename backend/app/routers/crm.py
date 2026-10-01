"""CRM, удержание, деньги и платформенные модули админки."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..db import (AssetProblem, Booking, BookingResource, Campaign, Client, ClientAsset, Location,
                  LoyaltyTransaction, Resource, Review)
from ..deps import runtime
from ..events import event as log_event
from ..notify.service import settings_for
from ..policies import client_key, client_keys, normalize_phone, to_international
from ..timeutil import utc_iso

router = APIRouter(prefix="/api/admin", tags=["crm"])


def _guard(request: Request) -> None:
    from .admin import guard
    guard(request)


def _slug(tenant: str | None = Query(default=None)) -> str:
    from .admin import tenant_slug
    return tenant_slug(tenant)


def _commit_unique(session, message: str) -> None:
    """Повтор кода — ошибка ввода, а не сбой сервера.

    Коды локаций, ресурсов и абонементов уникальны в пределах бизнеса. Без этой
    обёртки опечатка владельца доходила до базы и возвращалась в панель пятисоткой
    «ошибка сервера», по которой непонятно, что именно исправлять.
    """
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, message) from exc


def _client(row: Client) -> dict:
    return {
        "id": row.id, "name": row.name, "phone": row.phone, "lang": row.lang,
        "notes": row.notes, "tags": row.tags or [], "consent": row.consent,
        "blocked": row.blocked, "firstSeenAt": utc_iso(row.first_seen_at),
        "lastSeenAt": utc_iso(row.last_seen_at),
        "lastVisitAt": utc_iso(row.last_visit_at),
        "visits": row.visits_count, "noShows": row.no_show_count,
        "ltv": row.lifetime_value, "loyalty": row.loyalty_balance,
    }


@router.get("/clients", dependencies=[Depends(_guard)])
def clients(segment: str = "", q: str = "", slug: str = Depends(_slug)) -> dict:
    rows = runtime.store.list_clients(tenant_id=slug, segment=segment, query=q)
    return {"clients": [_client(row) for row in rows]}


@router.get("/clients/export", dependencies=[Depends(_guard)])
def export_clients(slug: str = Depends(_slug)) -> Response:
    """Выгрузка базы в CSV — тем же файлом её можно загрузить обратно.

    Маршрут объявлен раньше `/clients/{client_id}`: иначе шаблонный путь принял
    бы «export» за идентификатор клиента и вернул 404.
    """
    from .. import clients_csv

    body = clients_csv.export(runtime.store.list_clients(tenant_id=slug, limit=100_000))
    return Response(
        # BOM: без него Excel открывает кириллицу и испанские буквы кракозябрами.
        content="\ufeff" + body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="clients-{slug}.csv"'},
    )


@router.get("/clients/{client_id}", dependencies=[Depends(_guard)])
def client_detail(client_id: str, slug: str = Depends(_slug)) -> dict:
    row = runtime.store.get_client(client_id, tenant_id=slug)
    if not row:
        raise HTTPException(404, "Клиент не найден")
    bookings = runtime.store.client_bookings(client_id, tenant_id=slug)
    return {**_client(row), "bookings": [{
        "id": b.id, "serviceId": b.service_id, "masterId": b.master_id,
        "start": utc_iso(b.start_at), "status": b.status,
        "priceAmount": b.price_amount, "paidAmount": b.paid_amount, "currency": b.currency,
        "promoCode": b.promo_code, "source": b.source,
    } for b in bookings]}


class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=5, max_length=40)
    lang: str = Field(default="ru", pattern="^(ru|es|en)$")
    notes: str = Field(default="", max_length=2000)
    consent: bool = True


@router.post("/clients", dependencies=[Depends(_guard)])
def create_client(payload: ClientCreate, slug: str = Depends(_slug)) -> dict:
    """Клиент, заведённый вручную: пришёл без записи, позвонил, старый постоянный.

    Телефон нормализуется так же, как при записи, — иначе тот же человек,
    записавшийся через виджет, заведётся второй карточкой, и вся история
    (визиты, неявки, LTV) разъедется на две.
    """
    tenant = runtime.for_tenant(slug).tenant
    country = tenant.salon.get("phoneCountry", "")
    phone = client_key(payload.phone, country)
    if len(normalize_phone(payload.phone)) < 7:
        raise HTTPException(400, "Нужен корректный телефон")

    existing = runtime.store.client_by_phone(phone, tenant_id=slug,
                                             aliases=client_keys(payload.phone, country))
    if existing:
        # Не заводим дубль и не переписываем чужую карточку молча: панель
        # откроет существующую, а решение — за администратором.
        raise HTTPException(409, detail={"error": "Клиент с таким телефоном уже есть",
                                         "clientId": existing.id, "name": existing.name})

    row = runtime.store.upsert_client(tenant_id=slug, phone=phone, name=payload.name,
                                      lang=payload.lang, consent=payload.consent,
                                      aliases=client_keys(payload.phone, country))
    if payload.notes.strip():
        row = runtime.store.patch_client(row.id, tenant_id=slug,
                                         fields={"notes": payload.notes.strip()}) or row
    return {"ok": True, "client": _client(row)}


class ClientImport(BaseModel):
    csv: str = Field(min_length=1, max_length=2_000_000)
    # Первый заход — предпросмотр: чужой файл всегда грязный, и владелец должен
    # увидеть, что именно приедет, до того как оно приедет.
    commit: bool = False


@router.post("/clients/import", dependencies=[Depends(_guard)])
def import_clients(payload: ClientImport, slug: str = Depends(_slug)) -> dict:
    """Загрузка клиентской базы из CSV. Без `commit` — только отчёт."""
    from .. import clients_csv

    country = runtime.for_tenant(slug).tenant.salon.get("phoneCountry", "")
    rows, missing = clients_csv.parse(payload.csv, country=country)
    if missing:
        raise HTTPException(400, "В файле нет колонки с телефоном — без неё клиента не завести")
    if not rows:
        raise HTTPException(400, "В файле нет ни одной строки с данными")
    return clients_csv.apply(runtime.store, rows, tenant_id=slug, country=country,
                             commit=payload.commit)


# Названия колонок по-русски: «в файле не хватает phone» — это сообщение для
# разработчика, а читает его владелец салона.
_COLUMN_TITLES = {"phone": "телефон", "date": "дата", "time": "время визита",
                  "service": "услуга", "master": "мастер"}


class VisitsImport(BaseModel):
    csv: str = Field(min_length=1, max_length=4_000_000)
    commit: bool = False


@router.post("/visits/import", dependencies=[Depends(_guard)])
def import_visits(payload: VisitsImport, slug: str = Depends(_slug)) -> dict:
    """История визитов из CSV. Без `commit` — только отчёт.

    Записи заводятся мимо календаря и мимо очереди уведомлений: прошлогодний
    визит не должен ни появиться в календаре мастера, ни превратиться в
    напоминание «завтра в 15:00». Подробности — в `visits_csv`.
    """
    from .. import visits_csv

    tenant = runtime.for_tenant(slug).tenant
    country = tenant.salon.get("phoneCountry", "")
    rows, missing = visits_csv.parse(payload.csv, tenant=tenant, country=country)
    if missing:
        raise HTTPException(400, "В файле не хватает колонок: "
                            + ", ".join(_COLUMN_TITLES.get(name, name) for name in missing))
    if not rows:
        raise HTTPException(400, "В файле нет ни одной строки с данными")
    return visits_csv.apply(runtime.store, rows, tenant=tenant, country=country,
                            commit=payload.commit)


class ClientPatch(BaseModel):
    name: str | None = None
    lang: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    consent: bool | None = None
    blocked: bool | None = None


@router.patch("/clients/{client_id}", dependencies=[Depends(_guard)])
def patch_client(client_id: str, payload: ClientPatch, slug: str = Depends(_slug)) -> dict:
    row = runtime.store.patch_client(client_id, tenant_id=slug,
                                     fields=payload.model_dump(exclude_none=True))
    if not row:
        raise HTTPException(404, "Клиент не найден")
    return {"ok": True, "client": _client(row)}


class WaitlistCreate(BaseModel):
    name: str
    phone: str
    lang: str = "ru"
    serviceId: str  # noqa: N815
    masterId: str = ""  # noqa: N815
    dateFrom: str  # noqa: N815
    dateTo: str  # noqa: N815
    timeFrom: str = ""  # noqa: N815
    timeTo: str = ""  # noqa: N815


@router.get("/waitlist", dependencies=[Depends(_guard)])
def waitlist(status: str = "waiting", slug: str = Depends(_slug)) -> dict:
    rows = runtime.store.list_waitlist(tenant_id=slug, status=status)
    return {"entries": [{
        "id": r.id, "clientId": r.client_id, "serviceId": r.service_id,
        "masterId": r.master_id, "dateFrom": r.date_from, "dateTo": r.date_to,
        "timeFrom": r.time_from, "timeTo": r.time_to, "status": r.status,
        "offerExpiresAt": utc_iso(r.offer_expires_at),
    } for r in rows]}


@router.post("/waitlist", dependencies=[Depends(_guard)])
def add_waitlist(payload: WaitlistCreate, slug: str = Depends(_slug)) -> dict:
    tenant = runtime.for_tenant(slug).tenant
    if not tenant.service(payload.serviceId):
        raise HTTPException(400, "Услуга не найдена")
    country = tenant.salon.get("phoneCountry", "")
    client = runtime.store.upsert_client(tenant_id=slug, phone=client_key(payload.phone, country),
                                         name=payload.name, lang=payload.lang,
                                         aliases=client_keys(payload.phone, country))
    row = runtime.store.add_waitlist(
        tenant_id=slug, client_id=client.id, service_id=payload.serviceId,
        master_id=payload.masterId, date_from=payload.dateFrom, date_to=payload.dateTo,
        time_from=payload.timeFrom, time_to=payload.timeTo)
    return {"ok": True, "id": row.id}


class CampaignCreate(BaseModel):
    name: str
    segment: str = Field(pattern="^(all|inactive|first_time|frequent|no_show)$")
    message: str = Field(min_length=1, max_length=2000)


@router.get("/campaigns", dependencies=[Depends(_guard)])
def campaigns(slug: str = Depends(_slug)) -> dict:
    return {"campaigns": [{
        "id": c.id, "name": c.name, "segment": c.segment, "message": c.message,
        "status": c.status, "recipients": c.recipients_count, "sent": c.sent_count,
        "createdAt": utc_iso(c.created_at),
    } for c in runtime.store.list_campaigns(tenant_id=slug)]}


@router.post("/campaigns", dependencies=[Depends(_guard)])
def create_campaign(payload: CampaignCreate, slug: str = Depends(_slug)) -> dict:
    row = runtime.store.create_campaign(tenant_id=slug, **payload.model_dump())
    return {"ok": True, "id": row.id}


@router.post("/campaigns/{campaign_id}/send", dependencies=[Depends(_guard)])
def send_campaign(campaign_id: str, slug: str = Depends(_slug)) -> dict:
    tenant = runtime.for_tenant(slug).tenant
    with runtime.store.session_factory() as session:
        campaign = session.get(Campaign, campaign_id)
        if not campaign or campaign.tenant_id != slug:
            raise HTTPException(404, "Кампания не найдена")
        if campaign.status == "sent":
            return {"ok": True, "queued": campaign.sent_count, "idempotent": True}
        recipients = runtime.store.list_clients(tenant_id=slug,
                                                segment="" if campaign.segment == "all" else campaign.segment)
        recipients = [c for c in recipients if c.consent and not c.blocked]
        settings = settings_for(tenant)
        queued = 0
        for client in recipients:
            task = runtime.store.enqueue_notification(
                notification_id=f"campaign-{campaign.id}-{client.id}", tenant_id=slug,
                booking_id="", type="campaign", audience="client", provider=settings.provider,
                channel=settings.client_channel,
                recipient=to_international(client.phone, tenant.salon.get("phoneCountry")),
                body=campaign.message, scheduled_at=datetime.now(timezone.utc))
            queued += int(task is not None)
        campaign.recipients_count, campaign.sent_count, campaign.status = len(recipients), queued, "sent"
        session.commit()
    return {"ok": True, "queued": queued}


class PaymentPatch(BaseModel):
    paidAmount: int = Field(ge=0)  # noqa: N815
    paymentMethod: str = Field(pattern="^(cash|card|transfer|certificate|membership)$")  # noqa: N815
    discountAmount: int = Field(default=0, ge=0)  # noqa: N815
    loyaltyPoints: int = Field(default=0, ge=0)  # noqa: N815
    # Абонемент или сертификат, которым закрывают визит. С ним `paidAmount` и
    # `paymentMethod` не нужны: сумма визита ноль, а способ берётся из вида
    # актива — панель не должна угадывать, membership это или certificate.
    assetId: str | None = None  # noqa: N815


@router.patch("/bookings/{booking_id}/payment", dependencies=[Depends(_guard)])
def payment(booking_id: str, payload: PaymentPatch, slug: str = Depends(_slug)) -> dict:
    before = runtime.store.get_booking(booking_id, tenant_id=slug)
    if not before:
        raise HTTPException(404, "Запись не найдена")

    if payload.assetId:
        # Баллы и абонемент вместе не считаем: это две разные механики скидки,
        # и их сумма на одном визите почти всегда означает ошибку ввода.
        if payload.loyaltyPoints:
            raise HTTPException(409, "Баллы и абонемент на одном визите не складываем")
        try:
            row = runtime.store.pay_with_asset(booking_id, tenant_id=slug,
                                               asset_id=payload.assetId,
                                               discount_amount=payload.discountAmount)
        except AssetProblem as exc:
            raise HTTPException(409, str(exc)) from exc
        log_event("payment.saved", tenant=slug, booking=booking_id, method=row.payment_method,
                  asset=row.asset_id, amount=row.paid_amount, discount=payload.discountAmount)
        return {"ok": True, "paidAmount": row.paid_amount, "method": row.payment_method,
                "assetId": row.asset_id, "loyaltyPoints": 0}

    if payload.loyaltyPoints:
        if not before.client_id:
            raise HTTPException(409, "У записи нет карточки клиента")
        if payload.loyaltyPoints > max(0, before.price_amount - payload.discountAmount):
            raise HTTPException(409, "Баллами нельзя списать больше стоимости визита")
        try:
            runtime.store.change_loyalty(
                tenant_id=slug, client_id=before.client_id, points=-payload.loyaltyPoints,
                reason="Оплата баллами", booking_id=booking_id, idempotent=True)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    row = runtime.store.set_payment(booking_id, tenant_id=slug, paid_amount=payload.paidAmount,
                                    payment_method=payload.paymentMethod,
                                    discount_amount=payload.discountAmount)
    if not row:
        raise HTTPException(404, "Запись не найдена")
    log_event("payment.saved", tenant=slug, booking=booking_id, method=row.payment_method,
              amount=row.paid_amount, discount=payload.discountAmount,
              points=payload.loyaltyPoints)
    return {"ok": True, "paidAmount": row.paid_amount, "method": row.payment_method,
            "loyaltyPoints": payload.loyaltyPoints}


@router.get("/finance", dependencies=[Depends(_guard)])
def finance(days: int = Query(default=30, ge=1, le=366), slug: str = Depends(_slug)) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rt = runtime.for_tenant(slug)
    with runtime.store.session_factory() as session:
        period_rows = list(session.scalars(select(Booking).where(
            Booking.tenant_id == slug, Booking.start_at >= since)).all())
    rows = [b for b in period_rows if b.status == "completed"]
    revenue = sum(int(b.paid_amount or 0) for b in rows)
    paid = [b for b in rows if b.paid_amount]
    by_master: dict[str, int] = {}
    by_service: dict[str, int] = {}
    by_method: dict[str, int] = {}
    payroll: dict[str, int] = {}
    # Визит по абонементу денег в кассу не приносит — они пришли при его продаже.
    # Но услуга оказана, и владелец должен видеть, на сколько именно.
    by_asset = sum(int(b.price_amount or 0) for b in rows
                   if b.payment_method in ("membership", "certificate"))
    by_source: dict[str, dict[str, int]] = {}
    by_promo: dict[str, dict[str, int]] = {}
    by_weekday: dict[str, int] = {}
    for b in rows:
        by_master[b.master_id] = by_master.get(b.master_id, 0) + b.paid_amount
        by_service[b.service_id] = by_service.get(b.service_id, 0) + b.paid_amount
        by_method[b.payment_method or "unpaid"] = by_method.get(b.payment_method or "unpaid", 0) + b.paid_amount
        master = rt.tenant.master(b.master_id) or {}
        value = int(master.get("commissionValue") or 0)
        # Процент мастеру считается от стоимости работы, а не от денег в кассе.
        # Визит по абонементу кассу не пополняет — но стрижку мастер сделал, и
        # без этой подмены зарплата за неё вышла бы нулевой.
        base = int(b.price_amount or 0) if b.asset_id else int(b.paid_amount or 0)
        payroll[b.master_id] = payroll.get(b.master_id, 0) + (
            base * value // 100 if master.get("commissionType", "percent") == "percent" else value)
        by_weekday[str(b.start_at.weekday())] = by_weekday.get(str(b.start_at.weekday()), 0) + 1
    for b in period_rows:
        source = b.source or "direct"
        item = by_source.setdefault(source, {"bookings": 0, "completed": 0, "revenue": 0})
        item["bookings"] += 1
        item["completed"] += int(b.status == "completed")
        item["revenue"] += int(b.paid_amount or 0)
        if b.promo_code:
            promo = by_promo.setdefault(b.promo_code, {"bookings": 0, "completed": 0, "revenue": 0})
            promo["bookings"] += 1
            promo["completed"] += int(b.status == "completed")
            promo["revenue"] += int(b.paid_amount or 0)
    return {
        "revenue": revenue, "averageCheck": revenue // len(paid) if paid else 0,
        "visits": len(rows), "currency": next((b.currency for b in rows), "UYU"),
        "byMaster": by_master, "byService": by_service, "byMethod": by_method, "payroll": payroll,
        "byAsset": by_asset,
        "bySource": by_source, "byPromo": by_promo, "byWeekday": by_weekday,
    }


@router.get("/retention", dependencies=[Depends(_guard)])
def retention(slug: str = Depends(_slug)) -> dict:
    clients = runtime.store.list_clients(tenant_id=slug)
    repeat = sum(1 for c in clients if c.visits_count >= 2)
    return {
        "clients": len(clients), "new": sum(1 for c in clients if c.visits_count <= 1),
        "repeat": repeat, "repeatRate": round(repeat / len(clients) * 100, 1) if clients else 0,
        "averageLtv": sum(c.lifetime_value for c in clients) // len(clients) if clients else 0,
        "inactive60": len(runtime.store.list_clients(tenant_id=slug, segment="inactive")),
    }


class LocationCreate(BaseModel):
    code: str
    name: str
    address: str = ""
    timezone: str = ""


@router.get("/locations", dependencies=[Depends(_guard)])
def locations(slug: str = Depends(_slug)) -> dict:
    with runtime.store.session_factory() as s:
        locs = list(s.scalars(select(Location).where(Location.tenant_id == slug)).all())
        resources = list(s.scalars(select(Resource).where(Resource.tenant_id == slug)).all())
    return {"locations": [{"id": x.id, "code": x.code, "name": x.name, "address": x.address,
                            "timezone": x.timezone, "active": x.active} for x in locs],
            "resources": [{"id": x.id, "locationId": x.location_id, "code": x.code,
                           "name": x.name, "kind": x.kind, "capacity": x.capacity,
                           "active": x.active} for x in resources]}


@router.post("/locations", dependencies=[Depends(_guard)])
def create_location(payload: LocationCreate, slug: str = Depends(_slug)) -> dict:
    with runtime.store.session_factory() as s:
        row = Location(tenant_id=slug, **payload.model_dump()); s.add(row)
        _commit_unique(s, "Локация с таким кодом уже есть")
        return {"ok": True, "id": row.id}


class LocationPatch(BaseModel):
    code: str | None = None
    name: str | None = None
    address: str | None = None
    timezone: str | None = None
    active: bool | None = None


@router.patch("/locations/{location_id}", dependencies=[Depends(_guard)])
def patch_location(location_id: str, payload: LocationPatch, slug: str = Depends(_slug)) -> dict:
    with runtime.store.session_factory() as s:
        row = s.get(Location, location_id)
        if not row or row.tenant_id != slug:
            raise HTTPException(404, "Филиал не найден")
        for key, value in payload.model_dump(exclude_none=True).items():
            setattr(row, key, value)
        _commit_unique(s, "Филиал с таким кодом уже есть")
        return {"ok": True, "id": row.id}


@router.delete("/locations/{location_id}", dependencies=[Depends(_guard)])
def delete_location(location_id: str, slug: str = Depends(_slug)) -> dict:
    """Удаление филиала. Пока к нему привязаны мастера — отказ с именами.

    Мастер, чей филиал исчез, пропадает из записи молча: клиент видит «нет
    свободных мастеров» и уходит. Пусть владелец сначала переведёт людей.
    """
    tenant = runtime.for_tenant(slug).tenant
    attached = [m.get("name") or m.get("id") for m in tenant.masters
                if m.get("locationId") == location_id]
    if attached:
        raise HTTPException(409, detail={"error": "К филиалу привязаны мастера",
                                         "masters": attached})
    with runtime.store.session_factory() as s:
        row = s.get(Location, location_id)
        if not row or row.tenant_id != slug:
            raise HTTPException(404, "Филиал не найден")
        # Ресурсы филиала не удаляем: у них ``ondelete=SET NULL``, кресло
        # переживает переезд салона и просто остаётся без адреса.
        s.delete(row)
        s.commit()
    return {"ok": True}


class ResourceCreate(BaseModel):
    code: str
    name: str
    kind: str = "chair"
    capacity: int = Field(default=1, ge=1, le=100)
    locationId: str | None = None  # noqa: N815


@router.post("/resources", dependencies=[Depends(_guard)])
def create_resource(payload: ResourceCreate, slug: str = Depends(_slug)) -> dict:
    with runtime.store.session_factory() as s:
        row = Resource(tenant_id=slug, code=payload.code, name=payload.name, kind=payload.kind,
                       capacity=payload.capacity, location_id=payload.locationId)
        s.add(row)
        _commit_unique(s, "Ресурс с таким кодом уже есть")
        return {"ok": True, "id": row.id}


class ResourcePatch(BaseModel):
    code: str | None = None
    name: str | None = None
    kind: str | None = None
    capacity: int | None = Field(default=None, ge=1, le=100)
    locationId: str | None = None  # noqa: N815
    active: bool | None = None


@router.patch("/resources/{resource_id}", dependencies=[Depends(_guard)])
def patch_resource(resource_id: str, payload: ResourcePatch, slug: str = Depends(_slug)) -> dict:
    with runtime.store.session_factory() as s:
        row = s.get(Resource, resource_id)
        if not row or row.tenant_id != slug:
            raise HTTPException(404, "Ресурс не найден")
        fields = payload.model_dump(exclude_none=True)
        if "locationId" in fields:
            row.location_id = fields.pop("locationId") or None
        for key, value in fields.items():
            setattr(row, key, value)
        _commit_unique(s, "Ресурс с таким кодом уже есть")
        return {"ok": True, "id": row.id}


@router.delete("/resources/{resource_id}", dependencies=[Depends(_guard)])
def delete_resource(resource_id: str, slug: str = Depends(_slug)) -> dict:
    """Удаление ресурса. Занятый будущими записями — только после их переноса.

    Связь с записью каскадная: удалив кресло, мы бы молча освободили его во
    всех уже созданных записях и посадили на него двоих.
    """
    now_ts = datetime.now(timezone.utc)
    with runtime.store.session_factory() as s:
        row = s.get(Resource, resource_id)
        if not row or row.tenant_id != slug:
            raise HTTPException(404, "Ресурс не найден")
        busy = s.scalar(select(func.count()).select_from(BookingResource).join(
            Booking, Booking.id == BookingResource.booking_id).where(
            BookingResource.resource_id == resource_id,
            Booking.status == "confirmed", Booking.start_at >= now_ts))
        if busy:
            raise HTTPException(409, detail={"error": "Ресурс занят будущими записями",
                                             "bookings": int(busy)})
        s.delete(row)
        s.commit()
    return {"ok": True}


class AssetCreate(BaseModel):
    clientId: str | None = None  # noqa: N815
    kind: str = Field(pattern="^(membership|certificate)$")
    code: str
    title: str
    balanceAmount: int = Field(default=0, ge=0)  # noqa: N815
    remainingUses: int = Field(default=0, ge=0)  # noqa: N815


@router.get("/assets", dependencies=[Depends(_guard)])
def assets(slug: str = Depends(_slug)) -> dict:
    with runtime.store.session_factory() as s:
        rows = list(s.scalars(select(ClientAsset).where(ClientAsset.tenant_id == slug)).all())
    return {"assets": [{"id": a.id, "clientId": a.client_id, "kind": a.kind, "code": a.code,
                        "title": a.title, "balance": a.balance_amount, "uses": a.remaining_uses,
                        "status": a.status} for a in rows]}


@router.post("/assets", dependencies=[Depends(_guard)])
def create_asset(payload: AssetCreate, slug: str = Depends(_slug)) -> dict:
    with runtime.store.session_factory() as s:
        row = ClientAsset(tenant_id=slug, client_id=payload.clientId, kind=payload.kind,
                          code=payload.code, title=payload.title, balance_amount=payload.balanceAmount,
                          remaining_uses=payload.remainingUses)
        s.add(row)
        _commit_unique(s, "Абонемент или сертификат с таким кодом уже есть")
        return {"ok": True, "id": row.id}


class LoyaltyPatch(BaseModel):
    points: int
    reason: str = ""
    bookingId: str | None = None  # noqa: N815


class AssetPatch(BaseModel):
    clientId: str | None = None  # noqa: N815
    code: str | None = None
    title: str | None = None
    balanceAmount: int | None = Field(default=None, ge=0)  # noqa: N815
    remainingUses: int | None = Field(default=None, ge=0)  # noqa: N815
    status: str | None = Field(default=None, pattern="^(active|spent|expired)$")


@router.patch("/assets/{asset_id}", dependencies=[Depends(_guard)])
def patch_asset(asset_id: str, payload: AssetPatch, slug: str = Depends(_slug)) -> dict:
    columns = {"clientId": "client_id", "balanceAmount": "balance_amount",
               "remainingUses": "remaining_uses"}
    with runtime.store.session_factory() as s:
        row = s.get(ClientAsset, asset_id)
        if not row or row.tenant_id != slug:
            raise HTTPException(404, "Абонемент не найден")
        for key, value in payload.model_dump(exclude_none=True).items():
            setattr(row, columns.get(key, key), value)
        _commit_unique(s, "Абонемент с таким кодом уже есть")
        return {"ok": True, "id": row.id}


@router.delete("/assets/{asset_id}", dependencies=[Depends(_guard)])
def delete_asset(asset_id: str, slug: str = Depends(_slug)) -> dict:
    """Удаление абонемента или сертификата. Это списание оплаченного —
    остаток возвращаем в ответе, чтобы панель показала, что именно исчезло."""
    with runtime.store.session_factory() as s:
        row = s.get(ClientAsset, asset_id)
        if not row or row.tenant_id != slug:
            raise HTTPException(404, "Абонемент не найден")
        left = {"balance": row.balance_amount, "uses": row.remaining_uses}
        s.delete(row)
        s.commit()
    return {"ok": True, **left}


@router.post("/clients/{client_id}/loyalty", dependencies=[Depends(_guard)])
def loyalty(client_id: str, payload: LoyaltyPatch, slug: str = Depends(_slug)) -> dict:
    try:
        balance = runtime.store.change_loyalty(
            tenant_id=slug, client_id=client_id, points=payload.points,
            reason=payload.reason, booking_id=payload.bookingId)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "balance": balance}


@router.get("/reviews", dependencies=[Depends(_guard)])
def reviews(slug: str = Depends(_slug)) -> dict:
    with runtime.store.session_factory() as s:
        rows = list(s.scalars(select(Review).where(Review.tenant_id == slug)
                              .order_by(Review.created_at.desc())).all())
    return {"reviews": [{"id": r.id, "bookingId": r.booking_id, "score": r.score,
                         "feedback": r.feedback, "status": r.status} for r in rows]}
