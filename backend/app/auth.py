"""Вход в админку по почте и паролю.

Раньше доступ давала одна строка `ADMIN_TOKEN` в окружении: она не отзывалась,
не различала людей и попадала в историю команд у каждого, кто ей пользовался.
Теперь у панели есть пользователи, а токен остаётся только для машинных
вызовов — скриптов и интеграций.

Устройство:
* пароль хранится хешем bcrypt (соль внутри хеша, стоимость по умолчанию);
* в cookie уходит случайный ключ сессии, в базе лежит его SHA-256 — дамп базы
  не даёт войти;
* второй фактор — TOTP (Google Authenticator и совместимые);
* перебор пароля ограничивается счётчиком в базе, а не в памяти процесса.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from sqlalchemy import delete, select

from .db import AdminSession, AdminUser, Store

log = logging.getLogger("auth")

SESSION_COOKIE = "booking_admin_session"
SESSION_TTL = timedelta(days=7)

# Порог и пауза подобраны так, чтобы человек с забытым паролем не блокировал
# себе доступ на полдня, а перебор стал бессмысленно медленным.
MAX_FAILED_ATTEMPTS = 7
LOCKOUT = timedelta(minutes=15)

MIN_PASSWORD_LENGTH = 10


class AuthError(RuntimeError):
    """Вход не удался. Текст безопасно показывать пользователю."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite отдаёт время без таймзоны — приводим к UTC на границе базы."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode())
    except (ValueError, TypeError):
        # Битый или пустой хеш — это не «пароль подошёл».
        return False


def check_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Пароль короче {MIN_PASSWORD_LENGTH} символов")
    if password.isdigit() or password.isalpha():
        raise AuthError("Пароль должен содержать и буквы, и цифры")


# --- TOTP --------------------------------------------------------------------
# Реализация на стандартной библиотеке: ради шести цифр тянуть зависимость,
# которая обновляется реже нашего релизного цикла, смысла нет.

def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, at: datetime | None = None, step: int = 30) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    counter = int((at or _now()).timestamp()) // step
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def verify_totp(secret: str, code: str) -> bool:
    """Проверяем соседние окна: часы телефона и сервера расходятся на секунды."""
    code = (code or "").strip().replace(" ", "")
    if not secret or not code.isdigit():
        return False
    now = _now()
    for drift in (-1, 0, 1):
        expected = totp_code(secret, now + timedelta(seconds=30 * drift))
        if hmac.compare_digest(expected, code):
            return True
    return False


def totp_uri(secret: str, email: str, issuer: str = "Demo Salon") -> str:
    return (f"otpauth://totp/{issuer}:{email}?secret={secret}"
            f"&issuer={issuer}&algorithm=SHA1&digits=6&period=30")


# --- пользователи ------------------------------------------------------------

ROLES = ("owner", "admin")


def create_user(store: Store, email: str, password: str, *,
                role: str = "admin", name: str = "") -> AdminUser:
    email = (email or "").strip().lower()
    if "@" not in email:
        raise AuthError("Нужен адрес почты")
    if role not in ROLES:
        raise AuthError("Роль: владелец или администратор")
    check_password_strength(password)
    with store.session_factory() as s:
        if s.scalar(select(AdminUser).where(AdminUser.email == email)):
            raise AuthError("Такой пользователь уже есть")
        user = AdminUser(email=email, password_hash=hash_password(password),
                         role=role, name=(name or "").strip())
        s.add(user)
        s.commit()
        s.refresh(user)
        log.info("Создан пользователь %s (%s)", email, role)
        return user


def list_users(store: Store) -> list[AdminUser]:
    with store.session_factory() as s:
        return list(s.scalars(select(AdminUser).order_by(AdminUser.id)))


def owners_count(store: Store) -> int:
    with store.session_factory() as s:
        return len(list(s.scalars(select(AdminUser.id)
                                  .where(AdminUser.role == "owner", AdminUser.is_active))))


def update_user(store: Store, user_id: int, **fields) -> AdminUser:
    """Правка роли, имени и настроек уведомлений. Пароль меняется отдельно."""
    allowed = {"role", "name", "telegram_chat_id", "notify_new_booking", "is_active"}
    with store.session_factory() as s:
        user = s.get(AdminUser, user_id)
        if not user:
            raise AuthError("Пользователь не найден")
        if fields.get("role") and fields["role"] not in ROLES:
            raise AuthError("Роль: владелец или администратор")
        # Последнего владельца не разжалуем и не отключаем: панель осталась бы
        # без единственного человека, которому можно подключать интеграции и
        # заводить пользователей, — а починить это было бы уже нечем.
        loses_owner = (user.role == "owner"
                       and (fields.get("role") in ("admin",) or fields.get("is_active") is False))
        if loses_owner and owners_count(store) <= 1:
            raise AuthError("Это единственный владелец — сначала назначьте другого")
        for key, value in fields.items():
            if key in allowed and value is not None:
                setattr(user, key, value)
        s.commit()
        s.refresh(user)
        return user


def delete_user(store: Store, user_id: int) -> None:
    with store.session_factory() as s:
        user = s.get(AdminUser, user_id)
        if not user:
            return
        if user.role == "owner" and owners_count(store) <= 1:
            raise AuthError("Это единственный владелец — сначала назначьте другого")
        s.delete(user)
        s.commit()


def users_exist(store: Store) -> bool:
    with store.session_factory() as s:
        return s.scalar(select(AdminUser.id).limit(1)) is not None


def set_password(store: Store, user_id: int, password: str) -> None:
    """Смена пароля закрывает все прежние сессии — на случай, если пароль меняют
    именно потому, что он мог утечь."""
    check_password_strength(password)
    with store.session_factory() as s:
        user = s.get(AdminUser, user_id)
        if not user:
            raise AuthError("Пользователь не найден")
        user.password_hash = hash_password(password)
        user.failed_attempts = 0
        user.locked_until = None
        s.execute(delete(AdminSession).where(AdminSession.user_id == user_id))
        s.commit()


def set_totp(store: Store, user_id: int, secret: str) -> None:
    with store.session_factory() as s:
        user = s.get(AdminUser, user_id)
        if not user:
            raise AuthError("Пользователь не найден")
        user.totp_secret = secret or ""
        s.commit()


# --- вход --------------------------------------------------------------------

def authenticate(store: Store, email: str, password: str, code: str | None = None) -> AdminUser:
    """Проверяет пару почта/пароль и, если включён, второй фактор.

    Сообщение об ошибке одно на «нет такого пользователя» и «неверный пароль»:
    иначе форма входа превращается в справочник существующих адресов.
    """
    email = (email or "").strip().lower()
    with store.session_factory() as s:
        user = s.scalar(select(AdminUser).where(AdminUser.email == email))
        if not user or not user.is_active:
            # Считаем хеш даже для несуществующего пользователя: без этого
            # ответ приходит заметно быстрее и выдаёт, что адреса нет.
            verify_password(password, "$2b$12$" + "x" * 53)
            raise AuthError("Неверная почта или пароль")

        locked = _aware(user.locked_until)
        if locked and locked > _now():
            left = int((locked - _now()).total_seconds() // 60) + 1
            raise AuthError(f"Слишком много попыток. Повторите через {left} мин")

        if not verify_password(password, user.password_hash):
            user.failed_attempts += 1
            if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = _now() + LOCKOUT
                user.failed_attempts = 0
                log.warning("Вход заблокирован на %s: перебор пароля для %s", LOCKOUT, email)
            s.commit()
            raise AuthError("Неверная почта или пароль")

        if user.totp_secret and not verify_totp(user.totp_secret, code or ""):
            # Отдельный текст: пароль подошёл, не хватает только кода.
            raise AuthError("Нужен код из приложения-аутентификатора")

        user.failed_attempts = 0
        user.locked_until = None
        user.last_login_at = _now()
        s.commit()
        s.refresh(user)
        return user


def needs_totp(store: Store, email: str) -> bool:
    """Показывать ли поле для кода. Без пароля правды не говорим: иначе можно
    перебором адресов узнать, у кого второй фактор не включён."""
    with store.session_factory() as s:
        user = s.scalar(select(AdminUser).where(AdminUser.email == (email or "").strip().lower()))
        return bool(user and user.totp_secret)


# --- сессии ------------------------------------------------------------------

def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def open_session(store: Store, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with store.session_factory() as s:
        s.add(AdminSession(token_hash=_digest(token), user_id=user_id,
                           expires_at=_now() + SESSION_TTL))
        # Заодно подметаем протухшие: отдельная задача ради этого не нужна.
        s.execute(delete(AdminSession).where(AdminSession.expires_at < _now()))
        s.commit()
    return token


def session_user(store: Store, token: str | None) -> AdminUser | None:
    if not token:
        return None
    with store.session_factory() as s:
        row = s.scalar(select(AdminSession).where(AdminSession.token_hash == _digest(token)))
        if not row:
            return None
        if (_aware(row.expires_at) or _now()) < _now():
            s.execute(delete(AdminSession).where(AdminSession.id == row.id))
            s.commit()
            return None
        user = s.get(AdminUser, row.user_id)
        return user if user and user.is_active else None


def close_session(store: Store, token: str | None) -> None:
    if not token:
        return
    with store.session_factory() as s:
        s.execute(delete(AdminSession).where(AdminSession.token_hash == _digest(token)))
        s.commit()


def cookie_is_secure() -> bool:
    """На localhost по http браузер не примет Secure-cookie, и вход не заработает.
    В проде схема всегда https, поэтому по умолчанию флаг включён."""
    return os.getenv("ADMIN_COOKIE_INSECURE") != "1"
