"""Публичное API виджета: каталог, слоты, запись и AI-диалог.

Бизнес определяется параметром ?tenant= (виджет подставляет его из data-tenant).
Если бизнес один — параметр можно не передавать.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..agent import AgentUnavailable
from ..events import event as log_event
from ..billing import LimitExceeded, check_and_count
from ..calendar_service import CalendarError
from ..deps import TenantRuntime, runtime
from ..db import Booking, Location, WaitlistEntry
from ..policies import check_signed_action, national_lengths, signed_action, slot_token
from ..slots import available_days, free_slots, nearby_slots, slot_at
from ..tenants import TenantError, registry
from ..timeutil import DATE_PATTERN, TIME_PATTERN, human_date, norm_lang, tz, zoned
from ..tools import ToolContext, ToolError

log = logging.getLogger("api")
router = APIRouter(prefix="/api", tags=["public"])


def current(tenant: str | None = Query(default=None, description="Код бизнеса")) -> TenantRuntime:
    """Бизнес из запроса. Единственный бизнес подставляется автоматически."""
    slugs = registry.slugs()
    if not slugs:
        raise HTTPException(503, "Ни один бизнес не настроен")
    slug = tenant or (slugs[0] if len(slugs) == 1 else None)
    if not slug:
        raise HTTPException(400, "Укажите бизнес: ?tenant=<код>")
    try:
        return runtime.for_tenant(slug)
    except TenantError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/config")
def get_config(lang: str = "ru", rt: TenantRuntime = Depends(current)) -> dict:
    t = rt.tenant
    code = norm_lang(lang)
    # Названия и описания услуг — на языке клиента: испанцу «Стрижка мужская»
    # ничего не говорит. Непереведённое поле отдаётся как есть, а не пустым.
    # Цена тоже переводится: в ней живёт текст вроде «(скидка 20%)», и без
    # перевода испанец читал «800 UYU (скидка 20%)».
    services = [
        {**s,
         "title": t.localized(s, "title", code),
         "desc": t.localized(s, "desc", code),
         "price": t.localized(s, "price", code)}
        for s in t.services
    ]
    with runtime.store.session_factory() as session:
        locations = list(session.scalars(select(Location).where(
            Location.tenant_id == t.slug, Location.active.is_(True)).order_by(Location.name)).all())
    return {
        "tenant": t.slug,
        "salon": {
            "name": t.salon.get("name"),
            "tagline": t.salon.get("tagline"),
            "address": t.salon.get("address"),
            "whatsapp": t.salon.get("whatsapp"),
            "instagram": t.salon.get("instagram"),
            "workHours": t.salon.get("workHours"),
            # Без рабочих дней виджет обещал клиенту «Пн–Вс» даже у салона с выходным.
            "workDays": t.salon.get("workDays"),
            "timezone": t.timezone,
            # Код страны и длины местного номера — чтобы виджет проверял телефон
            # ровно тем же правилом, что и запись. Свою копию правила он уже
            # разошёл с сервером: пропускал номер, на который сервер отвечал
            # отказом после сводки, и починить его клиенту было уже негде.
            "phoneCountry": t.salon.get("phoneCountry") or "",
            "phoneLengths": list(national_lengths(t.salon.get("phoneCountry") or "")),
        },
        "services": services,
        # Специализация мастера — тоже текст для клиента, а не служебное поле:
        # виджет подписывает им кнопку выбора, и «Marat — Стрижка, уход»
        # посреди испанского диалога выглядит поломкой.
        "masters": [
            {"id": m["id"], "name": m["name"], "role": t.localized(m, "role", code),
             "services": m.get("services", []), "locationId": m.get("locationId", "main")}
            for m in t.masters
        ],
        "locations": [{"id": x.id, "code": x.code, "name": x.name, "address": x.address}
                      for x in locations],
        # Что клиенту вообще разрешено делать самому. Страница «мои записи»
        # иначе показывала бы кнопку «перенести» там, где перенос выключен
        # политикой, и получала бы отказ уже после выбора нового времени.
        "actions": {
            "cancel": bool(t.policy("allowCancel", True)),
            "reschedule": bool(t.policy("allowReschedule", False)),
        },
        # Уходит ли клиенту хоть что-нибудь на самом деле. `console` — это лог
        # сервера, а не сообщение: обещать в виджете «пришлём ссылку в WhatsApp»
        # с таким провайдером значит соврать.
        "notifySends": bool(t.notifications.get("enabled", True) is not False
                            and (t.notifications.get("provider") or "console") != "console"),
        "calendarMode": rt.calendar.mode,
        "aiEnabled": rt.agent.available(),
    }


@router.get("/days")
def get_days(masterId: str, lang: str = "ru",  # noqa: N803
             rt: TenantRuntime = Depends(current)) -> dict:
    """lang — язык подписей дат; сами даты от языка не зависят."""
    master = rt.tenant.master(masterId)
    if not master:
        raise HTTPException(400, "Неизвестный мастер")
    return {"days": available_days(rt.tenant, master, lang=lang)}


@router.get("/slots")
def get_slots(masterId: str, serviceId: str,  # noqa: N803
              date: str = Query(pattern=DATE_PATTERN),
              rt: TenantRuntime = Depends(current)) -> dict:
    t = rt.tenant
    master, service = t.master(masterId), t.service(serviceId)
    if not master or not service:
        raise HTTPException(400, "Неизвестная услуга или мастер")
    if serviceId not in (master.get("services") or []):
        raise HTTPException(400, f"{master['name']} не делает «{service['title']}»")
    try:
        slots = free_slots(t, rt.calendar, master, service, date)
    except CalendarError as exc:
        log.error("Календарь недоступен: %s", exc)
        raise HTTPException(502, "Не удалось получить расписание из календаря") from exc
    return {
        "slots": [
            {"time": s["time"], "start": s["start"].isoformat(),
             "token": slot_token(masterId, serviceId, s["start"].isoformat(), t.slug)}
            for s in slots
        ]
    }


@router.get("/slot-check")
def check_slot(masterId: str, serviceId: str,  # noqa: N803
               date: str = Query(pattern=DATE_PATTERN),
               time: str = Query(pattern=TIME_PATTERN),
               rt: TenantRuntime = Depends(current)) -> dict:
    """Свободно ли время, которое клиент написал сам, и что предложить вместо.

    Кнопки показывают сетку салона, а мастер бывает свободен и между её
    делениями: после записи в 15:00 на 45 минут меню предлагает 17:00, но
    «хочу в 16» тоже можно принять. Если занято — два-три ближайших окна.
    """
    t = rt.tenant
    master, service = t.master(masterId), t.service(serviceId)
    if not master or not service:
        raise HTTPException(400, "Неизвестная услуга или мастер")
    if serviceId not in (master.get("services") or []):
        raise HTTPException(400, f"{master['name']} не делает «{service['title']}»")
    try:
        slot = slot_at(t, rt.calendar, master, service, date, time)
        nearest = [] if slot else nearby_slots(t, rt.calendar, master, service, date, time)
    except CalendarError as exc:
        log.error("Календарь недоступен: %s", exc)
        raise HTTPException(502, "Не удалось получить расписание из календаря") from exc

    def signed(s: dict) -> dict:
        return {"time": s["time"], "start": s["start"].isoformat(),
                "token": slot_token(masterId, serviceId, s["start"].isoformat(), t.slug)}

    return {"free": bool(slot), "slot": signed(slot) if slot else None,
            "nearest": [signed(s) for s in nearest]}


class TranscriptLine(BaseModel):
    """Одна реплика кнопочного сценария. Роль чужого вида считаем словами бота."""

    role: str = "assistant"
    text: str = Field(max_length=500)


class BookRequest(BaseModel):
    masterId: str  # noqa: N815 — контракт с фронтендом
    serviceId: str  # noqa: N815
    # Формат проверяем схемой: дальше дата уходит в расчёт слотов, и промах в
    # ней должен возвращаться клиенту с указанием поля, а не падать в 500.
    date: str = Field(pattern=DATE_PATTERN)
    time: str = Field(pattern=TIME_PATTERN)
    name: str
    phone: str
    comment: str = ""
    promoCode: str = ""  # noqa: N815
    source: str = "web"
    groupSize: int = Field(default=1, ge=1, le=100)  # noqa: N815
    token: str = ""
    # Согласие на подтверждение и напоминания. Виджет показывает галочку.
    notifyConsent: bool = True  # noqa: N815
    conversationId: str | None = None  # noqa: N815
    lang: str = "ru"
    # Переписка кнопочного сценария: что виджет показал клиенту и что тот выбрал.
    # Без неё панель показывала владельцу «без переписки» у каждой такой записи —
    # разговор был, но целиком оставался в браузере.
    transcript: list[TranscriptLine] = Field(default_factory=list, max_length=60)


def _refusal(exc: ToolError, *, conflict: bool = False) -> HTTPException:
    """Отказ инструмента → ответ клиенту.

    Текст сообщения написан для модели и всегда русский, а страницы клиента
    показывают отказ как есть. Поэтому рядом уезжает код: по нему виджет и
    страница «мои записи» берут свой перевод, а текст остаётся запасным
    вариантом для кода, которого фронтенд ещё не знает.
    """
    status = 409 if (conflict or exc.conflict) else 400
    # Причина отказа — в лог. Без неё в журнале остаётся голый «400 Bad Request»,
    # а клиент видит переведённое «занято»: два часа поломки на проде выглядели
    # как отсутствие свободных окон, пока не полезли в модель руками.
    log_event("booking.refused", code=exc.code or "—", status=status, reason=exc.message)
    return HTTPException(status, {"error": exc.message, "code": exc.code} if exc.code else exc.message)


def _save_transcript(conversation_id: str, lines: list[TranscriptLine]) -> None:
    """Дописывает реплики виджета в диалог, не дублируя уже сохранённые.

    Виджет присылает всю переписку целиком — так повтор запроса после отказа
    («это время только что заняли», и клиент выбрал другое) не рвёт разговор на
    два диалога. Сохранённый хвост пропускаем, иначе каждая новая попытка
    удваивала бы начало переписки.
    """
    if not lines:
        return
    saved = [(m["role"], m["content"]) for m in runtime.store.history(conversation_id, limit=200)]
    fresh = [("user" if x.role == "user" else "assistant", x.text) for x in lines]
    if fresh[:len(saved)] == saved:
        # Обычный случай: присланное — продолжение сохранённого. Дописываем хвост.
        fresh = fresh[len(saved):]
    else:
        # Диалог начинался в AI-чате и продолжился кнопками: порядок мог
        # разойтись, поэтому отбираем построчно, а не по префиксу.
        seen = set(saved)
        fresh = [line for line in fresh if line not in seen]
    for role, text in fresh:
        runtime.store.add_message(conversation_id, role, text)


@router.post("/book")
def book(payload: BookRequest, rt: TenantRuntime = Depends(current)) -> dict:
    """Кнопочный сценарий. Проходит ровно те же проверки, что и AI-путь."""
    t = rt.tenant
    master, service = t.master(payload.masterId), t.service(payload.serviceId)
    if not master or not service:
        raise HTTPException(400, "Неизвестная услуга или мастер")

    start = zoned(payload.date, payload.time, t.timezone)
    token = payload.token or slot_token(payload.masterId, payload.serviceId, start.isoformat(), t.slug)

    conv = runtime.store.conversation(payload.conversationId, tenant_id=t.slug, channel="web")
    # Переписку пишем до попытки записи: неудачная попытка — тоже разговор, и
    # владельцу важнее увидеть, на чём клиент остановился, чем пустую карточку.
    _save_transcript(conv.id, payload.transcript)
    # В кнопочном сценарии подтверждением служит само нажатие «Подтвердить».
    ctx = ToolContext(conversation_id=conv.id, history=[{"role": "user", "content": "да, подтверждаю"}],
                      lang=norm_lang(payload.lang))

    try:
        result = rt.tools.create_booking(
            service_id=payload.serviceId, master_id=payload.masterId, start=start.isoformat(),
            customer_name=payload.name, phone=payload.phone, confirmation_token=token,
            comment=payload.comment, notify_consent=payload.notifyConsent,
            promo_code=payload.promoCode, source=payload.source, group_size=payload.groupSize, ctx=ctx,
        )
    except ToolError as exc:
        raise _refusal(exc) from exc

    return {
        "ok": True,
        "bookingId": result["booking_id"],
        "htmlLink": result["html_link"],
        "conversationId": conv.id,
        "summary": {
            "service": result["service"], "master": result["master"],
            "date": result["date"], "dateLabel": human_date(result["date"], payload.lang),
            "time": result["time"], "duration": result["duration"], "address": result["address"],
        },
    }


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversationId: str | None = None  # noqa: N815
    # Язык клиента: страница сайта или язык первого сообщения. Виджет присылает его сам.
    lang: str = "ru"


@router.get("/manage/{client_id}")
def manage_bookings(client_id: str, token: str, rt: TenantRuntime = Depends(current)) -> dict:
    if not check_signed_action(token, "manage", rt.tenant.slug, client_id):
        raise HTTPException(403, "Ссылка недействительна")
    client = runtime.store.get_client(client_id, tenant_id=rt.tenant.slug)
    if not client or client.blocked:
        raise HTTPException(404, "Клиент не найден")
    now_ts = datetime.now(timezone.utc)
    bookings = [b for b in runtime.store.client_bookings(client_id, tenant_id=rt.tenant.slug)
                if b.status == "confirmed" and b.start_at >= now_ts]
    return {"client": {"name": client.name, "loyalty": client.loyalty_balance}, "bookings": [{
        "id": b.id, "serviceId": b.service_id, "masterId": b.master_id,
        "start": b.start_at.isoformat(), "confirmed": b.confirmed_by_client,
    } for b in bookings]}


@router.post("/manage/{client_id}/bookings/{booking_id}/confirm")
def manage_confirm(client_id: str, booking_id: str, token: str,
                   rt: TenantRuntime = Depends(current)) -> dict:
    if not check_signed_action(token, "manage", rt.tenant.slug, client_id):
        raise HTTPException(403, "Ссылка недействительна")
    booking = runtime.store.get_booking(booking_id, tenant_id=rt.tenant.slug)
    client = runtime.store.get_client(client_id, tenant_id=rt.tenant.slug)
    if not booking or booking.client_id != client_id or not client:
        raise HTTPException(404, "Запись не найдена")
    runtime.store.mark_client_confirmed(booking_id, tenant_id=rt.tenant.slug)
    return {"ok": True, "confirmed": True}


@router.post("/manage/{client_id}/bookings/{booking_id}/cancel")
def manage_cancel(client_id: str, booking_id: str, token: str,
                  rt: TenantRuntime = Depends(current)) -> dict:
    if not check_signed_action(token, "manage", rt.tenant.slug, client_id):
        raise HTTPException(403, "Ссылка недействительна")
    booking = runtime.store.get_booking(booking_id, tenant_id=rt.tenant.slug)
    client = runtime.store.get_client(client_id, tenant_id=rt.tenant.slug)
    if not booking or booking.client_id != client_id or not client:
        raise HTTPException(404, "Запись не найдена")
    result = rt.tools.cancel_booking(
        booking_id=booking_id,
        ctx=ToolContext(conversation_id=f"manage-{client_id}", channel="web",
                        history=[{"role": "user", "content": "да, подтверждаю"}], lang=client.lang))
    return {"ok": True, **result}


class ManageReschedule(BaseModel):
    masterId: str  # noqa: N815
    start: str
    slotToken: str  # noqa: N815


@router.post("/manage/{client_id}/bookings/{booking_id}/reschedule")
def manage_reschedule(client_id: str, booking_id: str, token: str, payload: ManageReschedule,
                      rt: TenantRuntime = Depends(current)) -> dict:
    if not check_signed_action(token, "manage", rt.tenant.slug, client_id):
        raise HTTPException(403, "Ссылка недействительна")
    booking = runtime.store.get_booking(booking_id, tenant_id=rt.tenant.slug)
    client = runtime.store.get_client(client_id, tenant_id=rt.tenant.slug)
    if not booking or booking.client_id != client_id or not client:
        raise HTTPException(404, "Запись не найдена")
    try:
        result = rt.tools.reschedule_booking(
            booking_id=booking_id, master_id=payload.masterId, start=payload.start,
            confirmation_token=payload.slotToken,
            ctx=ToolContext(conversation_id=f"manage-{client_id}", channel="web",
                            history=[{"role": "user", "content": "да, подтверждаю"}], lang=client.lang))
    except ToolError as exc:
        raise _refusal(exc) from exc
    return {"ok": True, "booking": result}


class ReviewSubmit(BaseModel):
    score: int = Field(ge=1, le=5)
    feedback: str = Field(default="", max_length=2000)


@router.post("/reviews/{review_id}")
def submit_review(review_id: str, token: str, payload: ReviewSubmit,
                  rt: TenantRuntime = Depends(current)) -> dict:
    if not check_signed_action(token, "review", rt.tenant.slug, review_id):
        raise HTTPException(403, "Ссылка недействительна")
    row = runtime.store.submit_review(review_id, score=payload.score, feedback=payload.feedback)
    if not row or row.tenant_id != rt.tenant.slug:
        raise HTTPException(404, "Запрос отзыва не найден")
    if payload.score <= 4:
        from ..notify.service import settings_for
        settings = settings_for(rt.tenant)
        if settings.owner_recipient:
            channel = "telegram" if settings.owner_provider == "telegram" else (
                "email" if settings.owner_provider == "email" else "whatsapp")
            runtime.store.enqueue_notification(
                notification_id=f"review-owner-{row.id}", tenant_id=rt.tenant.slug,
                booking_id="", type="campaign", audience="owner",
                provider=settings.owner_provider, channel=channel,
                recipient=settings.owner_recipient,
                body=f"Новый отзыв: {payload.score}/5. {payload.feedback or 'Без комментария'}",
                scheduled_at=datetime.now(timezone.utc))
    return {"ok": True, "public": payload.score == 5,
            "googleMaps": rt.tenant.salon.get("googleMapsUrl", "") if payload.score == 5 else ""}


@router.get("/waitlist/{entry_id}/offer")
def waitlist_offer(entry_id: str, token: str, rt: TenantRuntime = Depends(current)) -> dict:
    with runtime.store.session_factory() as session:
        entry = session.get(WaitlistEntry, entry_id)
        if not entry or entry.tenant_id != rt.tenant.slug \
                or not check_signed_action(token, "waitlist", rt.tenant.slug, entry_id):
            raise HTTPException(404, "Предложение не найдено")
        active = entry.status == "offered" and bool(entry.offer_expires_at) \
            and entry.offer_expires_at.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
        return {"id": entry.id, "active": active, "serviceId": entry.service_id,
                "bookingId": entry.offered_booking_id, "expiresAt": entry.offer_expires_at}


@router.post("/waitlist/{entry_id}/accept")
def accept_waitlist(entry_id: str, token: str, rt: TenantRuntime = Depends(current)) -> dict:
    if not check_signed_action(token, "waitlist", rt.tenant.slug, entry_id):
        raise HTTPException(403, "Ссылка недействительна")
    with runtime.store.session_factory() as session:
        entry = session.get(WaitlistEntry, entry_id)
        if not entry or entry.tenant_id != rt.tenant.slug or entry.status != "offered" \
                or not entry.offer_expires_at:
            raise HTTPException(409, "Предложение уже недоступно")
        expires = entry.offer_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= datetime.now(timezone.utc):
            entry.status = "expired"; session.commit()
            raise HTTPException(409, "Время предложения истекло")
        old = session.get(Booking, entry.offered_booking_id)
        client = runtime.store.get_client(entry.client_id, tenant_id=rt.tenant.slug)
        if not old or old.status != "cancelled" or not client:
            raise HTTPException(409, "Слот уже занят")
        old.idempotency_key = None
        session.commit()
        start = old.start_at if old.start_at.tzinfo else old.start_at.replace(tzinfo=timezone.utc)
        # Подпись слота считается по времени в поясе салона: `create_booking`
        # приводит присланное время к нему же, и подпись, снятая с UTC-строки,
        # не совпадала — лист ожидания отвечал «это время не предлагалось».
        start = start.astimezone(tz(rt.tenant.timezone))
    ctx = ToolContext(conversation_id=f"waitlist-{entry.id}", channel="web", lang=client.lang,
                      history=[{"role": "user", "content": "да, подтверждаю"}])
    try:
        result = rt.tools.create_booking(
            service_id=entry.service_id, master_id=old.master_id, start=start.isoformat(),
            customer_name=client.name, phone=client.phone,
            confirmation_token=slot_token(old.master_id, entry.service_id, start.isoformat(), rt.tenant.slug),
            notify_consent=client.consent, source="waitlist", ctx=ctx)
    except ToolError as exc:
        raise _refusal(exc, conflict=True) from exc
    with runtime.store.session_factory() as session:
        rows = list(session.scalars(select(WaitlistEntry).where(
            WaitlistEntry.offered_booking_id == old.id, WaitlistEntry.status == "offered")).all())
        for row in rows:
            row.status = "booked" if row.id == entry_id else "expired"
        session.commit()
    return {"ok": True, "booking": result}


@router.get("/manage-link/{client_id}")
def manage_link(client_id: str, rt: TenantRuntime = Depends(current)) -> dict:
    """Токен возвращается только после знания client_id; сам id случайный 128-битный."""
    if not runtime.store.get_client(client_id, tenant_id=rt.tenant.slug):
        raise HTTPException(404, "Клиент не найден")
    return {"clientId": client_id, "token": signed_action("manage", rt.tenant.slug, client_id)}


@router.post("/chat")
def chat(payload: ChatRequest, rt: TenantRuntime = Depends(current)) -> dict:
    """Свободный диалог. Модель говорит, действия выполняет backend."""
    t = rt.tenant
    if not rt.agent.available():
        raise HTTPException(409, "AI-диалог выключен — включите его в настройках")

    conv = runtime.store.conversation(payload.conversationId, tenant_id=t.slug, channel="web")
    per_minute = int(t.policy("rateLimitPerMinute", 20) or 0)
    if not runtime.limiter.allow(f"chat:{t.slug}:{conv.id}", per_minute):
        raise HTTPException(429, "Слишком много сообщений подряд — подождите минуту")

    # Лимит тарифа на AI-сообщения: считаем каждое обращение клиента.
    try:
        check_and_count(runtime.store, "aiMessages", tenant_id=t.slug)
    except LimitExceeded as exc:
        log.error("Лимит AI-сообщений: %s", exc.message)
        if t.autonomous:
            fallback = rt.tools.recover(exc.message)
            return {"conversationId": conv.id, "text": fallback["message"], "handoff": False,
                    "booking": None, "limit": exc.metric, "suggestions": [], "fallback": True}
        fallback = rt.tools.handoff_to_human(reason=exc.message)
        return {"conversationId": conv.id, "text": fallback["message"],
                "handoff": True, "booking": None, "limit": exc.metric, "suggestions": []}

    history = runtime.store.history(conv.id)
    runtime.store.add_message(conv.id, "user", payload.message)
    lang = norm_lang(payload.lang)
    ctx = ToolContext(conversation_id=conv.id,
                      history=[*history, {"role": "user", "content": payload.message}],
                      lang=lang)

    try:
        result = rt.agent.reply(payload.message, ctx, lang=lang)
    except AgentUnavailable as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — клиент не должен видеть трейс
        log.exception("Диалог упал")
        reason = f"Сбой агента: {exc}"
        if t.autonomous:
            fallback = rt.tools.recover(reason, ctx=ctx)
            runtime.store.add_message(conv.id, "assistant", fallback["message"])
            return {"conversationId": conv.id, "text": fallback["message"], "handoff": False,
                    "booking": None, "suggestions": [], "fallback": True}
        fallback = rt.tools.handoff_to_human(reason=reason, ctx=ctx)
        runtime.store.add_message(conv.id, "assistant", fallback["message"])
        return {"conversationId": conv.id, "text": fallback["message"], "handoff": True,
                "booking": None, "suggestions": []}

    runtime.store.add_message(conv.id, "assistant", result["text"])
    booking = next((a["result"] for a in result["actions"] if a["tool"] == "create_booking" and a["ok"]), None)
    return {
        "conversationId": conv.id,
        "text": result["text"],
        "handoff": result["handoff"],
        "booking": booking,
        # Кнопки под ответом: клиенту не обязательно печатать — можно просто нажать.
        "suggestions": result.get("suggestions") or [],
        "fallback": bool(result.get("fallback")),
    }
