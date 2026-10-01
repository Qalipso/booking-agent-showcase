"""Входящие от Telegram: один публичный адрес на бизнес.

Публичный по необходимости — Telegram ходит без авторизации. Защита в том, что
адрес содержит код бизнеса, а в заголовке приходит секрет, заданный при
`setWebhook`: без него апдейт отбрасывается. Иначе кто угодно, угадав адрес,
отмечал бы чужие записи «клиент не пришёл».
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Request

from .. import telegram, telegram_bot
from ..deps import runtime
from ..policies import webhook_secret
from ..tenants import registry

log = logging.getLogger("telegram.hook")
router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.post("/{slug}/webhook")
async def incoming(slug: str, request: Request,
                   x_telegram_bot_api_secret_token: str | None = Header(default=None)) -> dict:
    if not registry.exists(slug):
        raise HTTPException(404, "Бизнес не найден")
    if (x_telegram_bot_api_secret_token or "") != webhook_secret(slug):
        # 403, а не 401: у Telegram нет способа «войти», повторять бессмысленно.
        raise HTTPException(403, "Неверная подпись вебхука")

    tenant = registry.get(slug)
    token = (tenant.handoff.get("telegramBotToken") or "").strip()
    if not token:
        return {"ok": True}   # бота отключили — апдейты просто игнорируем

    try:
        update = await request.json()
    except ValueError:
        raise HTTPException(400, "Ожидается JSON") from None

    try:
        note = telegram_bot.handle_update(update, tenant, runtime.store, token)
    except telegram.TelegramError as exc:
        # Telegram повторяет апдейт при ошибке. Наши проблемы с отправкой —
        # не повод получать одно и то же нажатие снова и снова.
        log.error("[%s] Telegram отказал: %s", slug, exc)
        return {"ok": True}
    log.info("[%s] %s", slug, note)
    return {"ok": True}
