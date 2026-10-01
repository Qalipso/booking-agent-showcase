"""Вход мастера в свой кабинет — по личной ссылке и четырём цифрам.

Пароль здесь был бы вреден: мастера меняются, почта есть не у всех, а забытый
пароль в салоне означает звонок владельцу посреди рабочего дня. Ссылку владелец
выдаёт из панели, отправляет мастеру в тот же Telegram, где уже настроены
уведомления, и в любой момент отзывает — например, когда мастер уходит.

ПИН — второй фактор, и нужен он ровно потому, что ссылка живёт в переписке:
её пересылают, показывают на экране, она остаётся в чате уволившегося. Одной
утёкшей ссылки для входа мало — нужны ещё четыре цифры.

Цифры придумывает сам мастер при первом открытии ссылки, и они остаются за ним
навсегда. Так владельцу нечего диктовать и нечего забывать, а главное — ПИН не
знает никто, кроме мастера: в базе только хеш, в панели видно лишь, задан он
или нет. Забыл — владелец сбрасывает, и мастер задаёт новый по той же ссылке.

Перебор четырёх цифр закрыт счётчиком попыток: пять промахов — и ключ молчит
четверть часа. Счётчик в базе, а не в памяти процесса: перезапуск контейнера
не должен обнулять защиту.

Устройство повторяет вход в панель, где оно себя оправдало:
* в базе — только SHA-256 ключа и ключа сессии, дамп базы войти не даёт;
* сессия хранится строкой в базе, а не подписанным токеном, — поэтому отзыв
  ссылки закрывает уже открытые кабинеты немедленно;
* частота попыток ограничена: ключ короткий, и перебор должен быть бессмысленным.

Ссылка одна на мастера. Вторая выдача гасит первую: две живые ссылки у одного
человека — это ровно та ситуация, когда «отозвали» превращается в «отозвали одну
из».
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from .auth import hash_password, verify_password
from .db import MasterKey, MasterSession, Store

log = logging.getLogger("staff")

SESSION_COOKIE = "booking_master_session"
# Дольше админской (7 дней): телефон мастера — его личный, а вход по ссылке из
# переписки раз в неделю никто терпеть не станет.
SESSION_TTL = timedelta(days=60)

# Пять попыток на четыре цифры: человек, набравший ПИН криво, попадёт со второй,
# а перебор десяти тысяч комбинаций растягивается на недели.
MAX_PIN_ATTEMPTS = 5
PIN_LOCKOUT = timedelta(minutes=15)

# Комбинации, которые владелец продиктует не глядя, а угадают с первой попытки.
WEAK_PINS = {"0000", "1111", "2222", "3333", "4444", "5555", "6666", "7777",
             "8888", "9999", "1234", "4321", "0123", "1212", "2020", "1122"}


class StaffError(RuntimeError):
    """Вход не удался. Текст безопасно показывать мастеру."""

    def __init__(self, message: str, status: int = 401) -> None:
        super().__init__(message)
        self.status = status


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite отдаёт время без таймзоны — приводим к UTC на границе базы."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def check_pin(pin: str) -> None:
    """Придуманный ПИН годится? Требования ровно два, и оба объяснимы вслух."""
    pin = (pin or "").strip()
    if len(pin) != 4 or not pin.isdigit():
        raise StaffError("ПИН — это четыре цифры")
    if pin in WEAK_PINS:
        # «1234» и «0000» подбираются раньше, чем сработает счётчик попыток.
        raise StaffError("Такой ПИН слишком простой — придумайте другой")


def issue_key(store: Store, tenant_id: str, master_id: str) -> str:
    """Новая ссылка мастеру. Старая перестаёт работать в тот же миг.

    ПИН не задаётся здесь: его придумает сам мастер, открыв ссылку. Ключ
    возвращается ровно один раз — в базе лежит только хеш, и «покажите ещё раз»
    честно означает «выдайте новую».
    """
    key = secrets.token_urlsafe(24)
    with store.session_factory() as s:
        s.execute(delete(MasterKey).where(MasterKey.tenant_id == tenant_id,
                                          MasterKey.master_id == master_id))
        s.add(MasterKey(tenant_id=tenant_id, master_id=master_id, key_hash=_digest(key)))
        s.commit()
    log.info("[%s] выдана ссылка в кабинет мастера %s", tenant_id, master_id)
    return key


def reset_pin(store: Store, tenant_id: str, master_id: str) -> bool:
    """Мастер забыл ПИН. Ссылка остаётся прежней — он задаст новый по ней же.

    Отдельно от отзыва: забытый ПИН — рабочая мелочь, а не повод рассылать новую
    ссылку и объяснять, почему старая больше не открывается.
    """
    with store.session_factory() as s:
        row = s.scalar(select(MasterKey).where(MasterKey.tenant_id == tenant_id,
                                               MasterKey.master_id == master_id))
        if not row:
            return False
        row.pin_hash = ""
        row.pin_attempts = 0
        row.pin_locked_until = None
        s.commit()
    log.info("[%s] ПИН мастера %s сброшен — задаст новый при следующем входе",
             tenant_id, master_id)
    return True


def stage_of(store: Store, key: str) -> tuple[str, str, str]:
    """Что показать мастеру: «придумайте ПИН» или «введите ПИН».

    Отдельный шаг, потому что экран должен знать это до ввода. Отвечать на него
    не опаснее, чем на сам вход: неверный ПИН и так отличается от неверной
    ссылки — иначе мастер не понимал бы, что именно набрал не так.
    """
    if not key:
        raise StaffError("Ссылка не подошла")
    with store.session_factory() as s:
        row = s.scalar(select(MasterKey).where(MasterKey.key_hash == _digest(key)))
        if not row:
            raise StaffError("Ссылка не подошла")
        locked = _aware(row.pin_locked_until)
        if locked and locked > _now():
            minutes = max(1, int((locked - _now()).total_seconds() // 60) + 1)
            raise StaffError(f"Слишком много попыток. Попробуйте через {minutes} мин", 429)
        return ("setup" if not row.pin_hash else "pin"), row.tenant_id, row.master_id


def revoke_key(store: Store, tenant_id: str, master_id: str) -> bool:
    """Отзыв ссылки. Открытые по ней кабинеты закрываются вместе с ней."""
    with store.session_factory() as s:
        result = s.execute(delete(MasterKey).where(MasterKey.tenant_id == tenant_id,
                                                   MasterKey.master_id == master_id))
        s.commit()
    if result.rowcount:
        log.info("[%s] ссылка мастера %s отозвана", tenant_id, master_id)
    return bool(result.rowcount)


def key_status(store: Store, tenant_id: str, master_id: str) -> dict:
    """Есть ли у мастера доступ и заходил ли он. Самого ключа здесь нет и быть
    не может — он существует только в момент выдачи."""
    with store.session_factory() as s:
        row = s.scalar(select(MasterKey).where(MasterKey.tenant_id == tenant_id,
                                               MasterKey.master_id == master_id))
        locked = _aware(row.pin_locked_until) if row else None
        return {
            "issued": bool(row),
            # Владелец ПИНа не знает и знать не должен — но видеть, задан ли он,
            # обязан: «ПИН ещё не задан» у мастера, который клянётся, что вошёл,
            # означает, что ссылку открыл кто-то другой.
            "pinSet": bool(row and row.pin_hash),
            "createdAt": _aware(row.created_at).isoformat() if row else "",
            "lastSeenAt": (_aware(row.last_seen_at).isoformat()
                           if row and row.last_seen_at else ""),
            # Владельцу важно знать, что мастер сейчас не войдёт, — иначе
            # «у меня не открывается» разбирается вслепую.
            "lockedUntil": locked.isoformat() if locked and locked > _now() else "",
        }


def open_session(store: Store, key: str, pin: str) -> tuple[str, str, str]:
    """Проверяет ссылку и ПИН, открывает кабинет. Возвращает сессию и мастера.

    Если ПИН ещё не задан, первый вход его и задаёт: мастер придумывает четыре
    цифры сам, и дальше они спрашиваются при каждом входе с нового устройства.
    """
    if not key:
        raise StaffError("Ссылка не подошла")
    with store.session_factory() as s:
        row = s.scalar(select(MasterKey).where(MasterKey.key_hash == _digest(key)))
        if not row:
            # Ни намёка на причину: «такой ссылки нет» и «ссылку отозвали» —
            # разные ответы только для того, кто перебирает.
            raise StaffError("Ссылка не подошла")

        locked = _aware(row.pin_locked_until)
        if locked and locked > _now():
            minutes = max(1, int((locked - _now()).total_seconds() // 60) + 1)
            raise StaffError(f"Слишком много попыток. Попробуйте через {minutes} мин", 429)

        if not row.pin_hash:
            # Первый вход: мастер задаёт себе ПИН.
            check_pin(pin)
            row.pin_hash = hash_password(pin.strip())
            row.pin_attempts = 0
            log.info("[%s] мастер %s задал ПИН", row.tenant_id, row.master_id)
        elif not verify_password(pin or "", row.pin_hash):
            row.pin_attempts += 1
            left = MAX_PIN_ATTEMPTS - row.pin_attempts
            if left <= 0:
                row.pin_attempts = 0
                row.pin_locked_until = _now() + PIN_LOCKOUT
                s.commit()
                log.warning("[%s] кабинет мастера %s закрыт на %s мин: ПИН не подошёл",
                            row.tenant_id, row.master_id, int(PIN_LOCKOUT.total_seconds() // 60))
                raise StaffError("Слишком много попыток. Попробуйте через "
                                 f"{int(PIN_LOCKOUT.total_seconds() // 60)} мин", 429)
            s.commit()
            raise StaffError(f"Неверный ПИН. Осталось попыток: {left}")

        token = secrets.token_urlsafe(32)
        s.add(MasterSession(token_hash=_digest(token), key_id=row.id,
                            expires_at=_now() + SESSION_TTL))
        row.last_seen_at = _now()
        row.pin_attempts = 0
        row.pin_locked_until = None
        # Заодно подметаем протухшие: отдельная задача ради этого не нужна.
        s.execute(delete(MasterSession).where(MasterSession.expires_at < _now()))
        s.commit()
        return token, row.tenant_id, row.master_id


def session_master(store: Store, token: str | None) -> tuple[str, str] | None:
    """Кто открыл кабинет: (бизнес, мастер). None — никто, надо войти заново."""
    if not token:
        return None
    with store.session_factory() as s:
        row = s.scalar(select(MasterSession).where(MasterSession.token_hash == _digest(token)))
        if not row:
            return None
        if (_aware(row.expires_at) or _now()) < _now():
            s.execute(delete(MasterSession).where(MasterSession.id == row.id))
            s.commit()
            return None
        key = s.get(MasterKey, row.key_id)
        if not key:
            return None
        return key.tenant_id, key.master_id


def close_session(store: Store, token: str | None) -> None:
    if not token:
        return
    with store.session_factory() as s:
        s.execute(delete(MasterSession).where(MasterSession.token_hash == _digest(token)))
        s.commit()
