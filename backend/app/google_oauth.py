"""Подключение Google Calendar через вход в аккаунт.

Владелец салона нажимает «Подключить Google», выбирает аккаунт — refresh token
приходит на callback и сохраняется в конфигурации бизнеса. Руками ничего вводить
не нужно, кроме Client ID и Secret приложения (одни на весь сервис).
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

log = logging.getLogger("google-oauth")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
CALENDAR_LIST_URL = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
CALENDARS_URL = "https://www.googleapis.com/calendar/v3/calendars"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
]
STATE_TTL = 600  # 10 минут на прохождение согласия


class OAuthError(RuntimeError):
    """Понятная ошибка для админки."""


@dataclass
class PendingAuth:
    tenant: str
    created_at: float
    redirect_uri: str


_pending: dict[str, PendingAuth] = {}


def client_credentials(tenant) -> tuple[str, str]:
    """Client ID/Secret: из окружения (общие на сервис) либо из настроек бизнеса."""
    google = tenant.google  # секреты подмешаны из окружения и хранилища
    client_id = google.get("clientId")
    client_secret = google.get("clientSecret")
    if not (client_id and client_secret):
        raise OAuthError(
            "Сначала заполните Client ID и Client Secret — их выдаёт Google Cloud Console "
            "(APIs & Services → Credentials → OAuth client ID, тип «Web application»)."
        )
    return client_id, client_secret


def build_auth_url(tenant, redirect_uri: str) -> str:
    client_id, _ = client_credentials(tenant)
    state = secrets.token_urlsafe(24)
    _cleanup()
    _pending[state] = PendingAuth(tenant=tenant.slug, created_at=time.time(), redirect_uri=redirect_uri)

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",       # нужен refresh token
        "prompt": "consent",            # иначе Google повторно его не выдаст
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def consume_state(state: str) -> PendingAuth:
    _cleanup()
    pending = _pending.pop(state or "", None)
    if not pending:
        raise OAuthError("Ссылка авторизации устарела — начните подключение заново")
    return pending


def _cleanup() -> None:
    now = time.time()
    for key in [k for k, v in _pending.items() if now - v.created_at > STATE_TTL]:
        _pending.pop(key, None)


def exchange_code(tenant, code: str, redirect_uri: str) -> dict:
    """Код авторизации → refresh token. Возвращает {'refresh_token', 'email'}."""
    client_id, client_secret = client_credentials(tenant)
    try:
        res = httpx.post(TOKEN_URL, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=20)
        res.raise_for_status()
    except httpx.HTTPError as exc:
        detail = getattr(exc, "response", None)
        message = detail.text if detail is not None else str(exc)
        raise OAuthError(f"Google не выдал токен: {message}") from exc

    payload = res.json()
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise OAuthError(
            "Google вернул доступ без refresh token. Отзовите доступ приложения в "
            "myaccount.google.com/permissions и подключитесь заново."
        )

    email = ""
    try:
        info = httpx.get(USERINFO_URL, headers={"Authorization": f"Bearer {payload['access_token']}"},
                         timeout=10)
        email = info.json().get("email", "") if info.is_success else ""
    except httpx.HTTPError:  # почта — приятное дополнение, не повод падать
        log.warning("Не удалось прочитать email аккаунта")

    return {"refresh_token": refresh_token, "email": email}


def access_token(tenant) -> str:
    """Свежий access token по сохранённому refresh token."""
    client_id, client_secret = client_credentials(tenant)
    refresh = tenant.google.get("refreshToken")
    if not refresh:
        raise OAuthError("Google-аккаунт не подключён")
    try:
        res = httpx.post(TOKEN_URL, data={
            "client_id": client_id, "client_secret": client_secret,
            "refresh_token": refresh, "grant_type": "refresh_token",
        }, timeout=20)
        res.raise_for_status()
    except httpx.HTTPError as exc:
        raise OAuthError("Google отклонил сохранённый доступ — подключитесь заново") from exc
    return res.json()["access_token"]


def create_calendar(tenant, summary: str, description: str = "") -> dict:
    """Заводит отдельный календарь и возвращает {'id', 'title'}.

    Календарь создаётся в том же аккаунте, которым подключён салон, поэтому
    отдельная выдача доступа не нужна: он сразу виден владельцу и доступен на
    запись тому же токену, которым бот пишет события.

    Зачем вообще отдельный: у всех новых мастеров ``calendarId`` — «primary»,
    то есть один и тот же основной календарь аккаунта. Два мастера на одном
    календаре видят занятость друг друга как свою — салон теряет половину окон
    на ровном месте, и заметно это становится только по жалобам клиентов.
    """
    token = access_token(tenant)
    try:
        res = httpx.post(
            CALENDARS_URL,
            headers={"Authorization": f"Bearer {token}"},
            json={"summary": summary, "description": description, "timeZone": tenant.timezone},
            timeout=20,
        )
        res.raise_for_status()
    except httpx.HTTPError as exc:
        raise OAuthError("Google не дал создать календарь — попробуйте ещё раз") from exc
    data = res.json()
    return {"id": data["id"], "title": data.get("summary") or summary}


def list_calendars(tenant) -> list[dict]:
    """Календари аккаунта — чтобы мастера выбирали свой из списка, а не вводили ID."""
    token = access_token(tenant)
    try:
        res = httpx.get(CALENDAR_LIST_URL, headers={"Authorization": f"Bearer {token}"},
                        params={"minAccessRole": "writer", "maxResults": 250}, timeout=20)
        res.raise_for_status()
    except httpx.HTTPError as exc:
        raise OAuthError("Не удалось получить список календарей") from exc
    return [
        {
            "id": item["id"],
            "title": item.get("summary") or item["id"],
            "primary": bool(item.get("primary")),
            "role": item.get("accessRole"),
        }
        for item in res.json().get("items", [])
    ]
