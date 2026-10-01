"""Подключение учётной записи Twilio.

Как у Telegram: владелец вводит пару ключей один раз, всё остальное сервис
узнаёт сам. Имя аккаунта и его состояние приходят из ``Accounts/{sid}``, список
номеров — из ``IncomingPhoneNumbers``, поэтому отправителя не нужно набирать
руками и ошибаться в формате.

Проверка ключей — настоящий запрос к Twilio: «сохранено» само по себе не
значит «работает», а неверный Auth Token обнаруживается иначе только первым
несостоявшимся напоминанием клиенту.
"""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger("twilio")

API = "https://api.twilio.com/2010-04-01"
TIMEOUT = 10.0

# Номер песочницы один на весь Twilio: с него шлют, пока не одобрен свой
# отправитель. Узнаём его, чтобы подсказать владельцу, а не заставлять искать.
SANDBOX_WHATSAPP = "+14155238886"


class TwilioError(RuntimeError):
    """Текст безопасно показывать в админке."""


def _get(sid: str, token: str, path: str) -> dict:
    if not (sid and token):
        raise TwilioError("Нужны Account SID и Auth Token")
    if not sid.startswith("AC"):
        raise TwilioError("Account SID начинается с «AC» — похоже, вставлено не то поле")
    try:
        response = httpx.get(f"{API}/{path}", auth=(sid, token), timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise TwilioError(f"Twilio недоступен: {exc}") from exc

    if response.status_code in (401, 403):
        raise TwilioError("Twilio не принял ключи — проверьте Account SID и Auth Token")
    if response.status_code == 404:
        raise TwilioError("Такого аккаунта в Twilio нет — проверьте Account SID")
    if response.status_code >= 400:
        try:
            message = response.json().get("message")
        except ValueError:
            message = ""
        raise TwilioError(message or f"Twilio ответил {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise TwilioError("Twilio вернул неожиданный ответ") from exc


def account(sid: str, token: str) -> dict:
    """Чей это аккаунт и жив ли он. Единственная настоящая проверка ключей."""
    data = _get(sid, token, f"Accounts/{sid}.json")
    status = data.get("status") or ""
    if status in ("suspended", "closed"):
        raise TwilioError(f"Аккаунт Twilio {status}: сообщения отправляться не будут")
    return {"name": data.get("friendly_name") or sid, "status": status,
            "type": data.get("type") or ""}


def numbers(sid: str, token: str) -> list[dict]:
    """Купленные номера. Пустой список — не ошибка: у песочницы номеров нет."""
    data = _get(sid, token, f"Accounts/{sid}/IncomingPhoneNumbers.json?PageSize=50")
    out = []
    for row in data.get("incoming_phone_numbers") or []:
        caps = row.get("capabilities") or {}
        out.append({
            "number": row.get("phone_number") or "",
            "label": row.get("friendly_name") or row.get("phone_number") or "",
            "sms": bool(caps.get("sms")),
        })
    return [n for n in out if n["number"]]
