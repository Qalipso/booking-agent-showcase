"""Обратная связь от провайдера: статусы доставки, ответы клиентов, очередь."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response

from ..deps import runtime
from ..notify import verify_twilio_signature
from ..policies import client_key, client_keys
from ..tenants import registry

log = logging.getLogger("notify")
router = APIRouter(prefix="/api/notifications", tags=["notifications"])

# Twilio ждёт TwiML: пустой ответ значит «сами клиенту ничего не шлём».
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


def _twilio_auth_token(tenant_slug: str | None = None) -> str:
    """Токен того бизнеса, чьи креды подписывали запрос.

    Webhook приходит без указания бизнеса, поэтому подпись проверяем против
    каждого настроенного токена — их единицы, а неподписанный запрос принимать
    нельзя: по нему можно объявить любое сообщение доставленным.
    """
    slugs = [tenant_slug] if tenant_slug else registry.slugs()
    for slug in slugs:
        try:
            token = registry.get(slug).notifications.get("twilioAuthToken")
        except Exception:  # noqa: BLE001
            continue
        if token:
            return token
    return ""


@router.post("/twilio-status")
async def twilio_status(request: Request,
                        tenant: str | None = Query(default=None),
                        x_twilio_signature: str = Header(default="")) -> dict:
    """Twilio сообщает, дошло ли сообщение. Без валидной подписи — 403."""
    form = dict((await request.form()).items())
    token = _twilio_auth_token(tenant)
    if not token:
        raise HTTPException(503, "Twilio не настроен")
    if not verify_twilio_signature(auth_token=token, url=str(request.url),
                                   params=form, signature=x_twilio_signature):
        log.warning("Отклонён webhook Twilio с неверной подписью")
        raise HTTPException(403, "Неверная подпись")

    updated = runtime.notifications.apply_provider_status(
        provider_message_id=str(form.get("MessageSid") or form.get("SmsSid") or ""),
        raw_status=str(form.get("MessageStatus") or form.get("SmsStatus") or ""),
    )
    return {"ok": True, "notification": updated.notification_id if updated else None}


@router.post("/twilio-inbound")
async def twilio_inbound(request: Request,
                         tenant: str | None = Query(default=None),
                         x_twilio_signature: str = Header(default="")) -> Response:
    """Клиент ответил на сообщение — доставляем ответ людям.

    В шаблонах написано «ответьте на это сообщение», и клиенты отвечают. До
    этого обработчика их ответ упирался в вебхук статусов, тот не понимал
    формат и отдавал ошибку: Twilio писал 11200, а салон не знал, что ему
    вообще написали.

    Отвечаем пустым TwiML: автоответ от имени салона — решение владельца, а не
    побочный эффект доставки.
    """
    form = dict((await request.form()).items())
    slug = tenant or (registry.slugs() or [""])[0]
    token = _twilio_auth_token(slug)
    if not token:
        raise HTTPException(503, "Twilio не настроен")
    if not verify_twilio_signature(auth_token=token, url=str(request.url),
                                   params=form, signature=x_twilio_signature):
        log.warning("Отклонён входящий Twilio с неверной подписью")
        raise HTTPException(403, "Неверная подпись")

    phone = str(form.get("From") or "").split(":", 1)[-1].strip()
    text = str(form.get("Body") or "").strip()
    if not (phone and text):
        return Response(content=EMPTY_TWIML, media_type="application/xml")

    try:
        # Через runtime, а не registry: только он подмешивает секреты, и без
        # него токен Telegram-бота пуст — ответ клиента «доставлять некуда».
        business = runtime.for_tenant(slug).tenant
    except Exception as exc:  # noqa: BLE001
        log.warning("Входящее для неизвестного бизнеса %s: %s", slug, exc)
        raise HTTPException(404, "Неизвестный бизнес") from exc

    # Переписка видна в панели целиком: владелец читает ответ в контексте, а не
    # одной вырванной строкой из Telegram.
    conv = runtime.store.conversation(None, tenant_id=slug, channel="whatsapp", external_id=phone)
    runtime.store.add_message(conv.id, "user", text)

    country = business.salon.get("phoneCountry", "")
    client = runtime.store.client_by_phone(client_key(phone, country), tenant_id=slug,
                                           aliases=client_keys(phone, country))
    delivered = runtime.notifications.notify_staff_client_reply(
        business, phone, text, client_name=(client.name if client else ""))
    log.info("Ответ клиента %s доставлен получателям: %s", phone, delivered)
    return Response(content=EMPTY_TWIML, media_type="application/xml")


def _admin_guard(request: Request, x_admin_token: str | None = Header(default=None)) -> None:
    """Тот же доступ, что и у остальной админки.

    Обёртка, а не прямой ``Depends(guard)``, — из-за кольцевого импорта: admin
    тянет уведомления. Request передаём обязательно: без него guard не увидит
    cookie сессии и падал с 500 ещё до проверки доступа.
    """
    from .admin import guard

    guard(request, x_admin_token)


@router.get("", dependencies=[Depends(_admin_guard)])
def list_queue(tenant: str | None = Query(default=None),
               booking: str | None = Query(default=None),
               limit: int = 100) -> dict:
    """Очередь уведомлений — чтобы администратор видел, что ушло и что не дошло."""
    tasks = runtime.store.list_notifications(tenant_id=tenant, booking_id=booking,
                                             limit=min(limit, 500))
    return {"notifications": [t.as_dict() for t in tasks]}
