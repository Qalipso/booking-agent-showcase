"""Каналы доставки.

Twilio закрывает WhatsApp и SMS одной интеграцией, Telegram — уведомления
владельцу, console — режим без кредов, чтобы гонять сценарий локально.

Провайдер возвращает ``SendResult`` или бросает ``SendError``. Различение
«временная ошибка / окончательная» — задача планировщика, здесь только флаг.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import smtplib
import ssl
from email.message import EmailMessage

import httpx

log = logging.getLogger("notify")

TWILIO_BASE = "https://api.twilio.com/2010-04-01"
TIMEOUT = 15.0


class SendError(Exception):
    def __init__(self, message: str, *, permanent: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.permanent = permanent


class SendResult:
    def __init__(self, provider_message_id: str | None, status: str = "sent") -> None:
        self.provider_message_id = provider_message_id
        self.status = status


def to_e164(phone: str) -> str:
    """E.164: +59899000101. Без плюса Twilio отвергнет номер."""
    value = re.sub(r"[^\d+]", "", str(phone or ""))
    return value if value.startswith("+") else f"+{value}"


def _permanent(status_code: int) -> bool:
    """4xx (кроме 429) чинить повтором нечем — неверный номер, шаблон или креды."""
    return 400 <= status_code < 500 and status_code != 429


def _send_twilio(*, cfg: dict, channel: str, to: str, body: str, template_name: str,
                 variables: dict, status_callback: str | None) -> SendResult:
    account_sid, auth_token = cfg.get("accountSid"), cfg.get("authToken")
    if not (account_sid and auth_token):
        raise SendError("Twilio: нет accountSid/authToken", permanent=True)

    sender = cfg.get("whatsappFrom") if channel == "whatsapp" else cfg.get("smsFrom")
    if not sender:
        raise SendError(f"Twilio: не задан номер отправителя для {channel}", permanent=True)

    params = {
        "To": f"whatsapp:{to_e164(to)}" if channel == "whatsapp" else to_e164(to),
        "From": f"whatsapp:{to_e164(sender)}" if channel == "whatsapp" else to_e164(sender),
    }

    content_sid = (cfg.get("contentSids") or {}).get(template_name) if channel == "whatsapp" else None
    if content_sid:
        params["ContentSid"] = content_sid
        # Twilio Content API нумерует переменные с 1 — порядок задаёт сам шаблон.
        params["ContentVariables"] = json.dumps(
            {str(i): str(v or "") for i, v in enumerate(variables.values(), start=1)},
            ensure_ascii=False,
        )
    else:
        params["Body"] = body
    if status_callback:
        params["StatusCallback"] = status_callback

    try:
        response = httpx.post(
            f"{TWILIO_BASE}/Accounts/{account_sid}/Messages.json",
            data=params, auth=(account_sid, auth_token), timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise SendError(f"Twilio недоступен: {exc}") from exc

    payload = _json(response)
    if response.status_code >= 400:
        raise SendError(f"Twilio {response.status_code}: {payload.get('message', 'ошибка отправки')}",
                        permanent=_permanent(response.status_code))
    return SendResult(payload.get("sid"))


def _send_telegram(*, cfg: dict, to: str, body: str,
                   buttons: list[list[dict]] | None = None) -> SendResult:
    """Владельцу удобнее в Telegram: не тратит шаблоны WhatsApp и не требует согласия."""
    token = cfg.get("botToken")
    if not (token and to):
        raise SendError("Telegram: нет botToken или chatId", permanent=True)
    params: dict = {"chat_id": to, "text": body, "disable_web_page_preview": True}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    try:
        response = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=params, timeout=TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise SendError(f"Telegram недоступен: {exc}") from exc

    payload = _json(response)
    if response.status_code >= 400 or payload.get("ok") is False:
        raise SendError(f"Telegram {response.status_code}: {payload.get('description', 'ошибка отправки')}",
                        permanent=_permanent(response.status_code))
    return SendResult(str((payload.get("result") or {}).get("message_id") or ""))


def _send_console(*, channel: str, to: str, body: str) -> SendResult:
    """Без кредов ничего не отправляем, но сценарий целиком виден в логе."""
    log.info("[console] %s → %s: %s", channel, to, body)
    return SendResult(f"console-{hashlib.sha1(f'{to}{body}'.encode()).hexdigest()[:16]}")


def _send_email(*, cfg: dict, to: str, body: str, template_name: str) -> SendResult:
    """Отправить внутреннее уведомление через обычный SMTP."""
    host = str(cfg.get("host") or "").strip()
    sender = str(cfg.get("from") or "").strip()
    if not (host and sender):
        raise SendError("Email: не заданы SMTP host или адрес отправителя", permanent=True)

    try:
        port = int(cfg.get("port") or 587)
    except (TypeError, ValueError) as exc:
        raise SendError("Email: некорректный SMTP port", permanent=True) from exc
    security = str(cfg.get("security") or "starttls").lower()
    if security not in {"starttls", "ssl", "plain"}:
        raise SendError("Email: неизвестный режим SMTP security", permanent=True)

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = {
        "owner_new_booking": "Новая запись — BookingAgent",
        "owner_booking_rescheduled": "Запись перенесена — BookingAgent",
        "owner_delivery_failed": "Не доставлено клиенту — BookingAgent",
    }.get(template_name, "Уведомление BookingAgent")
    message.set_content(body)

    username = str(cfg.get("username") or "").strip()
    password = str(cfg.get("password") or "")
    if username and not password:
        raise SendError("Email: для SMTP пользователя не задан пароль", permanent=True)

    client_cls = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
    try:
        with client_cls(host, port, timeout=TIMEOUT) as client:
            if security == "starttls":
                client.starttls(context=ssl.create_default_context())
            if username:
                client.login(username, password)
            client.send_message(message)
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused) as exc:
        raise SendError(f"Email отклонён SMTP-сервером: {exc}", permanent=True) from exc
    except (OSError, smtplib.SMTPException) as exc:
        raise SendError(f"SMTP недоступен: {exc}") from exc

    message_id = message.get("Message-ID") or hashlib.sha1(
        f"{to}{template_name}{body}".encode()
    ).hexdigest()
    return SendResult(f"smtp-{message_id.strip('<>')}")


def _json(response: httpx.Response) -> dict:
    try:
        return response.json()
    except ValueError:
        return {}


def send(*, provider: str, channel: str, to: str, body: str, template_name: str = "",
         variables: dict | None = None, cfg: dict | None = None,
         status_callback: str | None = None,
         buttons: list[list[dict]] | None = None) -> SendResult:
    """Единая точка отправки. `buttons` понимает только Telegram."""
    if not to:
        raise SendError("Не указан получатель", permanent=True)
    cfg = cfg or {}
    if provider == "twilio":
        return _send_twilio(cfg=cfg, channel=channel, to=to, body=body, template_name=template_name,
                            variables=variables or {}, status_callback=status_callback)
    if provider == "telegram":
        return _send_telegram(cfg=cfg, to=to, body=body, buttons=buttons)
    if provider == "email":
        if channel != "email":
            raise SendError(f"Email-провайдер не поддерживает канал {channel}", permanent=True)
        return _send_email(cfg=cfg, to=to, body=body, template_name=template_name)
    if provider == "console":
        return _send_console(channel=channel, to=to, body=body)
    raise SendError(f"Неизвестный провайдер: {provider}", permanent=True)


def verify_twilio_signature(*, auth_token: str, url: str, params: dict, signature: str) -> bool:
    """Подпись входящего webhook Twilio.

    Подписывается полный URL плюс пары параметров формы, отсортированные по ключу.
    https://www.twilio.com/docs/usage/security#validating-requests
    """
    if not (auth_token and signature):
        return False
    data = url + "".join(f"{k}{params[k]}" for k in sorted(params or {}))
    expected = base64.b64encode(
        hmac.new(auth_token.encode(), data.encode("utf-8"), hashlib.sha1).digest()
    ).decode()
    return hmac.compare_digest(expected, str(signature))


def normalize_twilio_status(status: str) -> str | None:
    """Статусы Twilio → наши."""
    return {
        "delivered": "delivered", "read": "delivered",
        "failed": "failed", "undelivered": "failed",
        "sent": "sent", "queued": "sent", "sending": "sent", "accepted": "sent",
    }.get((status or "").lower())
