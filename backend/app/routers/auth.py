"""Вход в админку: сессия по паролю, второй фактор, смена пароля.

Первый администратор заводится здесь же — пока в базе нет ни одного, форма
предлагает его создать. Открытым этот путь остаётся ровно до первого аккаунта:
дальше `/register` отвечает отказом, как и положено закрытой панели.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel

from .. import auth
from ..deps import runtime
from ..events import event as log_event
from ..policies import RateLimiter, user_link_code
from ..settings import admin_open, admin_token

log = logging.getLogger("admin.auth")
router = APIRouter(prefix="/api/admin/auth", tags=["admin"])

# Ограничение на IP поверх счётчика в базе: он защищает конкретный аккаунт,
# а это — от перебора адресов и от простого залива запросами.
LOGIN_ATTEMPTS_PER_MINUTE = 12
_attempts = RateLimiter()


class Credentials(BaseModel):
    email: str
    password: str
    code: str | None = None


class PasswordChange(BaseModel):
    currentPassword: str  # noqa: N815 — контракт с формой
    newPassword: str      # noqa: N815


class TotpConfirm(BaseModel):
    secret: str
    code: str


def _client(request: Request) -> str:
    return request.client.host if request.client else "?"


def _limit(request: Request) -> None:
    if not _attempts.allow(f"login:{_client(request)}", LOGIN_ATTEMPTS_PER_MINUTE):
        raise HTTPException(429, "Слишком много попыток — подождите минуту")


def current_user(request: Request):
    """Пользователь текущей сессии или None. Ошибку не бросает: тем же кодом
    пользуется страница, которой нужно просто узнать, вошли мы или нет."""
    token = request.cookies.get(auth.SESSION_COOKIE)
    return auth.session_user(runtime.store, token)


def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Нужен вход")
    return user


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        auth.SESSION_COOKIE, token,
        max_age=int(auth.SESSION_TTL.total_seconds()),
        httponly=True,           # из JavaScript ключ сессии не достать
        secure=auth.cookie_is_secure(),
        samesite="lax",          # защита от CSRF; переходы по ссылкам не ломает
        path="/",
    )


@router.get("/state")
def state(request: Request) -> dict:
    """Что показывать форме: создание первого администратора, вход или панель."""
    user = current_user(request)
    return {
        "authenticated": bool(user),
        "email": user.email if user else "",
        "name": user.name if user else "",
        # Панель по роли решает, какие разделы показывать. Права всё равно
        # проверяет сервер: спрятанный раздел — удобство, а не защита.
        "role": user.role if user else "",
        "totpEnabled": bool(user and user.totp_secret),
        "needsSetup": not auth.users_exist(runtime.store),
    }


@router.post("/register")
def register(payload: Credentials, request: Request, response: Response) -> dict:
    """Создание первого администратора. После него путь закрыт навсегда.

    Первый — всегда владелец: остальных заводит он сам, и если бы первый получал
    роль администратора, подключить интеграции и создать пользователей было бы
    некому.
    """
    _limit(request)
    if auth.users_exist(runtime.store):
        raise HTTPException(403, "Регистрация закрыта — администратор уже есть")
    try:
        user = auth.create_user(runtime.store, payload.email, payload.password, role="owner")
    except auth.AuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    _set_cookie(response, auth.open_session(runtime.store, user.id))
    log.info("Первый администратор создан: %s", user.email)
    return {"ok": True, "email": user.email}


@router.post("/login")
def login(payload: Credentials, request: Request, response: Response) -> dict:
    _limit(request)
    try:
        user = auth.authenticate(runtime.store, payload.email, payload.password, payload.code)
    except auth.AuthError as exc:
        # 401 и текст ошибки; какой именно фактор не сошёлся, знает только
        # тот, кто уже прошёл пароль.
        raise HTTPException(401, str(exc)) from exc
    _set_cookie(response, auth.open_session(runtime.store, user.id))
    log.info("Вход в админку: %s с %s", user.email, _client(request))
    log_event("admin.login", user=user.id, role=user.role)
    return {"ok": True, "email": user.email, "totpEnabled": bool(user.totp_secret)}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    auth.close_session(runtime.store, request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/password")
def change_password(payload: PasswordChange, request: Request, response: Response,
                    user=Depends(require_user)) -> dict:
    try:
        auth.authenticate(runtime.store, user.email, payload.currentPassword,
                          auth.totp_code(user.totp_secret) if user.totp_secret else None)
        auth.set_password(runtime.store, user.id, payload.newPassword)
    except auth.AuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    # Смена пароля закрыла все сессии, включая текущую — выдаём новую, чтобы
    # человека не выбросило из панели сразу после успешного действия.
    _set_cookie(response, auth.open_session(runtime.store, user.id))
    log.info("Пароль изменён: %s", user.email)
    return {"ok": True}


@router.post("/totp/start")
def totp_start(user=Depends(require_user)) -> dict:
    """Выдаёт секрет для аутентификатора. Включится только после подтверждения
    кодом — иначе можно запереть себя, сохранив секрет и потеряв телефон."""
    secret = auth.new_totp_secret()
    return {"secret": secret, "uri": auth.totp_uri(secret, user.email)}


@router.post("/totp/enable")
def totp_enable(payload: TotpConfirm, user=Depends(require_user)) -> dict:
    if not auth.verify_totp(payload.secret, payload.code):
        raise HTTPException(400, "Код не подошёл — проверьте время на телефоне")
    auth.set_totp(runtime.store, user.id, payload.secret)
    log.info("Двухфакторная аутентификация включена: %s", user.email)
    return {"ok": True}


def require_owner(request: Request, x_admin_token: str | None = Header(default=None)):
    """Список людей и их роли — дело владельца или доступа уровня сервера.

    Как и у интеграций: администратор не должен заводить себе равных, и прятать
    раздел в панели для этого недостаточно.

    Сессии, однако, бывает и нет. Машинный токен — это и есть доступ уровня
    сервера, он уже открывает записи и настройки; на локальной машине ту же роль
    играет `ADMIN_ALLOW_NO_TOKEN=1`. Пока здесь стояла проверка одной лишь
    сессии, оба получали 401 на списке пользователей — и панель, открытая для
    разработки, выбрасывала на форму входа при переходе на «Внутренние
    уведомления».

    Возвращается либо пользователь, либо None: у машинного доступа нет ни имени,
    ни почты, и вызывающий код обязан это учитывать.
    """
    user = current_user(request)
    if user:
        if user.role != "owner":
            raise HTTPException(403, "Раздел доступен только владельцу")
        return user

    token = admin_token()
    if not token:
        if admin_open():
            return None
        raise HTTPException(401, "Нужен вход")
    if hmac.compare_digest((x_admin_token or "").encode("utf-8", "ignore"), token.encode()):
        return None
    raise HTTPException(401, "Нужен вход")


class NewUser(BaseModel):
    email: str
    password: str
    name: str = ""
    role: str = "admin"


class UserPatch(BaseModel):
    name: str | None = None
    role: str | None = None
    notifyNewBooking: bool | None = None  # noqa: N815 — контракт с формой
    isActive: bool | None = None          # noqa: N815


def _user_view(u) -> dict:
    return {
        "id": u.id, "email": u.email, "name": u.name, "role": u.role,
        "isActive": bool(u.is_active),
        "telegramLinked": bool((u.telegram_chat_id or "").strip()),
        "notifyNewBooking": bool(u.notify_new_booking),
        "totpEnabled": bool(u.totp_secret),
    }


def _bot_username(slug: str) -> str:
    """Имя бота салона — из него собираются ссылки привязки. Пусто, если не подключён."""
    from .. import telegram
    from ..tenants import registry

    if not registry.exists(slug):
        return ""
    token = (registry.get(slug).handoff.get("telegramBotToken") or "").strip()
    if not token:
        return ""
    try:
        return telegram.me(token)["username"]
    except telegram.TelegramError:
        return ""   # состояние бота показывает свой экран, здесь это не ошибка


@router.get("/users")
def users(tenant: str | None = Query(default=None), _owner=Depends(require_owner)) -> dict:
    """Кто имеет доступ к панели и кому уходят внутренние уведомления."""
    from ..tenants import registry

    slug = tenant or (registry.slugs() or [""])[0]
    bot = _bot_username(slug)
    out = []
    for u in auth.list_users(runtime.store):
        view = _user_view(u)
        view["link"] = f"https://t.me/{bot}?start={user_link_code(u.id)}" if bot else ""
        out.append(view)
    return {"users": out, "botConnected": bool(bot), "bot": bot}


@router.post("/users/{user_id}/telegram/link")
def link_user_telegram(user_id: int, tenant: str | None = Query(default=None),
                       _owner=Depends(require_owner)) -> dict:
    """Ищет чат, из которого сотрудник открыл свою ссылку, и запоминает его."""
    from .. import telegram
    from ..tenants import registry

    slug = tenant or (registry.slugs() or [""])[0]
    if not registry.exists(slug):
        raise HTTPException(404, "Бизнес не найден")

    # Нажатие «Начать» вебхук привязывает сам — тогда кнопке остаётся подтвердить.
    user = next((u for u in auth.list_users(runtime.store) if u.id == user_id), None)
    if user and (user.telegram_chat_id or "").strip():
        return {"ok": True, "chatId": user.telegram_chat_id, "chatTitle": ""}

    token = (registry.get(slug).handoff.get("telegramBotToken") or "").strip()
    try:
        from ..policies import webhook_secret

        with telegram.webhook_paused(token, secret=webhook_secret(slug)):
            chat = telegram.find_chat_by_code(token, user_link_code(user_id))
    except telegram.TelegramError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not chat:
        raise HTTPException(422, "Сотрудник ещё не открыл ссылку — отправьте её "
                                 "и попросите нажать «Начать»")
    try:
        auth.update_user(runtime.store, user_id, telegram_chat_id=chat["id"])
    except auth.AuthError as exc:
        raise HTTPException(422, str(exc)) from exc
    log.info("Внутренние уведомления: пользователь %s → чат %s", user_id, chat["id"])
    return {"ok": True, "chatId": chat["id"], "chatTitle": chat["title"]}


@router.post("/users/{user_id}/telegram/test")
def test_user_telegram(user_id: int, tenant: str | None = Query(default=None),
                       _owner=Depends(require_owner)) -> dict:
    """Настоящее сообщение: «привязано» само по себе ничего не доказывает."""
    from .. import telegram
    from ..tenants import registry

    slug = tenant or (registry.slugs() or [""])[0]
    user = next((u for u in auth.list_users(runtime.store) if u.id == user_id), None)
    if not user or not (user.telegram_chat_id or "").strip():
        raise HTTPException(422, "Чат не привязан")
    token = (registry.get(slug).handoff.get("telegramBotToken") or "").strip()
    title = registry.get(slug).salon.get("name") or slug
    try:
        telegram.send(token, user.telegram_chat_id,
                      f"{title}: проверка связи. Сюда будут приходить новые записи салона.")
    except telegram.TelegramError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True}


@router.delete("/users/{user_id}/telegram")
def unlink_user_telegram(user_id: int, _owner=Depends(require_owner)) -> dict:
    auth.update_user(runtime.store, user_id, telegram_chat_id="")
    return {"ok": True}


@router.post("/users")
def add_user(payload: NewUser, _owner=Depends(require_owner)) -> dict:
    try:
        user = auth.create_user(runtime.store, payload.email, payload.password,
                                role=payload.role, name=payload.name)
    except auth.AuthError as exc:
        raise HTTPException(400, str(exc)) from exc
    log.info("Владелец завёл пользователя %s (%s)", user.email, user.role)
    return {"ok": True, "user": _user_view(user)}


@router.patch("/users/{user_id}")
def edit_user(user_id: int, payload: UserPatch, _owner=Depends(require_owner)) -> dict:
    try:
        user = auth.update_user(
            runtime.store, user_id, role=payload.role, name=payload.name,
            notify_new_booking=payload.notifyNewBooking, is_active=payload.isActive)
    except auth.AuthError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "user": _user_view(user)}


@router.delete("/users/{user_id}")
def remove_user(user_id: int, owner=Depends(require_owner)) -> dict:
    # owner=None — удаление машинным доступом: своей учётки у него нет, и
    # защищать её от самой себя не от чего.
    if owner is not None and user_id == owner.id:
        raise HTTPException(422, "Нельзя удалить самого себя")
    try:
        auth.delete_user(runtime.store, user_id)
    except auth.AuthError as exc:
        raise HTTPException(422, str(exc)) from exc
    log.info("Пользователь %s удалён: %s", user_id, owner.email if owner else "машинный доступ")
    return {"ok": True}


@router.post("/totp/disable")
def totp_disable(payload: Credentials, request: Request, user=Depends(require_user)) -> dict:
    """Выключение требует пароля: доступ к открытой вкладке не должен позволять
    снять второй фактор."""
    _limit(request)
    try:
        auth.authenticate(runtime.store, user.email, payload.password, payload.code)
    except auth.AuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    auth.set_totp(runtime.store, user.id, "")
    log.info("Двухфакторная аутентификация выключена: %s", user.email)
    return {"ok": True}
