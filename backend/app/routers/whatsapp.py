"""WhatsApp Business API. Включается на вкладке «Канал общения»."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from ..billing import period_key
from ..events import event as log_event
from ..deps import runtime
from ..policies import client_key, client_keys
from ..tenants import TenantError, registry
from ..timeutil import norm_lang
from ..tools import ToolContext, notify_admin
from ..transcribe import MAX_BYTES, TranscribeError, enabled as voice_enabled, transcribe

log = logging.getLogger("whatsapp")
router = APIRouter(prefix="/webhook/whatsapp", tags=["whatsapp"])

GRAPH = "https://graph.facebook.com/v21.0"

# Единственное, что бот отвечает клиенту сам, без модели, — и потому тоже на
# языке клиента.
CONFIRMED = {
    "ru": "Визит подтверждён. Спасибо!",
    "es": "Su cita está confirmada. ¡Gracias!",
    "en": "Your appointment is confirmed. Thank you!",
}

# Ответ на голосовое, которое не разобрали. На языке клиента: тот, кто говорит
# по-испански, не должен получить отписку по-русски. Молчание тут — худший
# вариант из всех: клиент уверен, что записался.
CANT_HEAR = {
    "ru": "Не получилось разобрать голосовое. Напишите, пожалуйста, текстом — отвечу сразу.",
    "es": "No pude escuchar tu audio. ¿Me lo escribís por texto? Te respondo enseguida.",
    "en": "I couldn't make out that voice message. Could you type it instead? I'll reply right away.",
}


def _runtime(slug: str):
    try:
        return runtime.for_tenant(slug)
    except TenantError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/{slug}")
def verify(slug: str, request: Request) -> Response:
    """Проверочный запрос Meta при подключении вебхука. У каждого бизнеса свой URL."""
    params = request.query_params
    channel = _runtime(slug).tenant.channel
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == channel.get("whatsappVerifyToken"):
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(403, "Неверный verify token")


@router.post("/{slug}")
async def incoming(slug: str, request: Request) -> dict:
    rt = _runtime(slug)
    tenant = rt.tenant
    if tenant.channel.get("kind") != "whatsapp":
        raise HTTPException(409, "WhatsApp-канал выключен")
    if not rt.agent.available():
        raise HTTPException(409, "AI-диалог выключен")

    payload = await request.json()
    for message in _extract_messages(payload):
        wa_id, text = message["from"], message["text"]
        if message["kind"] == "audio":
            text = _voice_to_text(rt, slug, message)
            if not text:
                continue   # клиенту уже ответили, владельцу — сообщили
        lang = _client_lang(rt, slug, wa_id)
        if re.search(r"\b(подтверждаю|confirmo|confirm|yes,? i confirm)\b", text, re.IGNORECASE):
            upcoming = runtime.store.upcoming_by_phone(wa_id, datetime.now(timezone.utc), tenant_id=slug)
            target = next((b for b in upcoming if b.requires_confirmation and not b.confirmed_by_client), None)
            if target:
                runtime.store.mark_client_confirmed(target.id, tenant_id=slug)
                _send(tenant, wa_id, CONFIRMED.get(lang, CONFIRMED["ru"]))
                continue
        conv = runtime.store.conversation(None, tenant_id=slug, channel="whatsapp", external_id=wa_id)
        per_minute = int(tenant.policy("rateLimitPerMinute", 20) or 0)
        if not runtime.limiter.allow(f"wa:{slug}:{wa_id}", per_minute):
            log.warning("Лимит сообщений для %s", wa_id)
            continue

        history = runtime.store.history(conv.id)
        # В диалоге видно, что клиент говорил, а не писал: администратор иначе
        # не поймёт, почему фразы в переписке звучат как речь.
        runtime.store.add_message(conv.id, "user", f"🎙 {text}" if message["kind"] == "audio" else text)
        # Язык клиента доходит и до инструментов, и до промпта. Без него модель
        # отвечала по-испански, а даты и названия услуг в её ответе приходили
        # из каталога по-русски — в одном сообщении оказывались оба языка.
        ctx = ToolContext(conversation_id=conv.id,
                          history=[*history, {"role": "user", "content": text}],
                          channel="whatsapp", lang=lang)
        try:
            result = rt.agent.reply(text, ctx, lang=lang)
            reply = result["text"]
            # В WhatsApp кнопок нет — варианты ответа дописываем строкой.
            chips = [c["label"] for c in result.get("suggestions") or []][:4]
            if chips:
                reply = f"{reply}\n\n" + " · ".join(chips)
        except Exception as exc:  # noqa: BLE001
            log.exception("Диалог WhatsApp упал")
            reason = f"Сбой агента: {exc}"
            reply = (rt.tools.recover(reason, ctx=ctx) if tenant.autonomous
                     else rt.tools.handoff_to_human(reason=reason, ctx=ctx))["message"]

        runtime.store.add_message(conv.id, "assistant", reply)
        _send(tenant, wa_id, reply)
        # Диалог целиком в логи не кладём: переписка живёт в базе и в панели, а
        # здесь важно, что сообщение пришло, дошло до агента и получило ответ.
        log_event("whatsapp.replied", tenant=slug, conversation=conv.id,
                  kind=message["kind"], lang=lang)

    return {"status": "ok"}


def _extract_messages(payload: dict) -> list[dict]:
    """Входящие, которые мы умеем обрабатывать: текст и голос.

    Голосовые раньше отбрасывались молча — вместе с клиентом, который был
    уверен, что записался. Всё остальное (картинки, документы, реакции) пока
    пропускаем так же, но это уже видно в логе.
    """
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for message in change.get("value", {}).get("messages", []):
                kind = message.get("type")
                if kind == "text":
                    out.append({"from": message["from"], "kind": "text",
                                "text": message["text"]["body"], "mediaId": ""})
                elif kind in ("audio", "voice"):
                    media = message.get(kind) or {}
                    out.append({"from": message["from"], "kind": "audio",
                                "text": "", "mediaId": str(media.get("id") or "")})
                else:
                    log.info("Пропущено сообщение типа %s", kind)
    return out


def _voice_to_text(rt, slug: str, message: dict) -> str:
    """Голосовое → текст. Пустая строка означает «клиенту уже ответили»."""
    tenant, wa_id = rt.tenant, message["from"]
    if not voice_enabled(tenant):
        # Выключено осознанно — клиенту отвечаем, владельца не дёргаем: он это
        # и настроил, а сигнал на каждое голосовое превратится в спам.
        _send(tenant, wa_id, CANT_HEAR.get(_client_lang(rt, slug, wa_id), CANT_HEAR["ru"]))
        return ""
    try:
        audio, mime = _download(tenant, message["mediaId"])
        text = transcribe(audio, tenant=tenant, mime=mime)
    except (TranscribeError, httpx.HTTPError) as exc:
        log.error("Голосовое не расшифровано: %s", exc)
        _send(tenant, wa_id, CANT_HEAR.get(_client_lang(rt, slug, wa_id), CANT_HEAR["ru"]))
        notify_admin(tenant, f"Клиент прислал голосовое, его не удалось разобрать: {exc}. "
                             "Напишите ему сами, если он не повторит текстом.")
        return ""
    # Расшифровка стоит денег провайдера — считаем её отдельно от сообщений
    # диалога, иначе привычка клиента диктовать вместо печати не видна в счёте.
    runtime.store.bump_usage(slug, "voiceMessages", period_key())
    return text


def _download(tenant, media_id: str) -> tuple[bytes, str]:
    """Файл из WhatsApp: сначала метаданные, потом сам файл — так у Meta."""
    token = tenant.channel.get("whatsappToken")
    if not (media_id and token):
        raise TranscribeError("WhatsApp не настроен — файл не забрать", permanent=True)
    headers = {"Authorization": f"Bearer {token}"}

    meta = httpx.get(f"{GRAPH}/{media_id}", headers=headers, timeout=10)
    meta.raise_for_status()
    info = meta.json() or {}
    # Размер известен до скачивания — на нём и отсекаем, чтобы не тянуть
    # получасовую запись через сервер и не платить за её расшифровку.
    if int(info.get("file_size") or 0) > MAX_BYTES:
        raise TranscribeError("Голосовое слишком длинное", permanent=True)
    url = str(info.get("url") or "")
    if not url:
        raise TranscribeError("Meta не отдала ссылку на файл", permanent=True)

    blob = httpx.get(url, headers=headers, timeout=30)
    blob.raise_for_status()
    if len(blob.content) > MAX_BYTES:
        raise TranscribeError("Голосовое слишком длинное", permanent=True)
    return blob.content, str(info.get("mime_type") or "audio/ogg").split(";")[0].strip()


def _client_lang(rt, slug: str, wa_id: str) -> str:
    """Язык клиента: из карточки, а если её нет — язык бизнеса.

    `ai.language` часто стоит в «auto»: это правило для модели, а не язык, и
    `norm_lang` превращал его в русский. Незнакомому номеру салона в Монтевидео
    надо отвечать по-испански, а не по-русски.
    """
    country = rt.tenant.salon.get("phoneCountry", "")
    client = runtime.store.client_by_phone(client_key(wa_id, country), tenant_id=slug,
                                           aliases=client_keys(wa_id, country))
    known = (client.lang if client else "") or ""
    return norm_lang(known) if known.strip() else rt.tenant.default_lang


def _send(tenant, to: str, text: str) -> None:
    channel = tenant.channel
    phone_id, token = channel.get("whatsappPhoneId"), channel.get("whatsappToken")
    if not (phone_id and token):
        log.error("WhatsApp не настроен — ответ не отправлен")
        return
    try:
        httpx.post(
            f"https://graph.facebook.com/v21.0/{phone_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}},
            timeout=10,
        ).raise_for_status()
    except Exception as exc:  # noqa: BLE001
        log.error("Не удалось отправить сообщение в WhatsApp: %s", exc)
