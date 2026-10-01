"""Правила, которые проверяет код, а не промпт."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime

SIGNING_KEY = (os.getenv("SLOT_SIGNING_KEY") or "demo-salon-dev-key").encode()

# «да, подтверждаю» на трёх языках салона.
CONFIRM_RE = re.compile(
    r"\b(да|давай|подтвержда\w*|подтверди\w*|записыва\w*|согласен|согласна|ок|окей|хорошо|"
    r"si|s[ií]\b|confirmo|confirmar|dale|vale|"
    r"yes|yeah|confirm|book it|ok)\b",
    re.IGNORECASE,
)
DECLINE_RE = re.compile(r"\b(нет|не надо|отмен\w*|no|nope|cancel\w*)\b", re.IGNORECASE)

# Телефон, но не дата, не ISO-время и не кусок идентификатора: требуем + или
# 7+ цифр подряд. В хвосте двоеточие не запрещаем — иначе «→ +598 91234567:
# текст» из лога отправки оставался бы незамаскированным, а это самая частая
# форма записи.
#
# Латинская буква по соседству отменяет совпадение: id записи — 32 hex-символа,
# и внутри него легко набирается восемь цифр подряд. Раньше такой id уезжал в
# лог как «cf0eddebacaf4c+***ba5f7e822e», и найти по нему запись было нельзя.
PHONE_RE = re.compile(r"(?<![\dA-Za-z\-:T])(\+\d[\d\s\-()]{6,}\d|\d{7,})(?![\dA-Za-z\-])")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def slot_token(master_id: str, service_id: str, start_iso: str, tenant_id: str = "") -> str:
    """Подпись слота: модель не может выдумать время, которого ей не показывали.
    Бизнес входит в подпись — токен одного салона не работает в другом."""
    payload = f"{tenant_id}|{master_id}|{service_id}|{start_iso}".encode()
    return hmac.new(SIGNING_KEY, payload, hashlib.sha256).hexdigest()[:32]


def check_slot_token(token: str, master_id: str, service_id: str, start_iso: str,
                     tenant_id: str = "") -> bool:
    expected = slot_token(master_id, service_id, start_iso, tenant_id)
    # compare_digest не принимает не-ASCII строки — сравниваем байты.
    return hmac.compare_digest((token or "").encode("utf-8", "ignore"), expected.encode())


def master_link_code(tenant_id: str, master_id: str) -> str:
    """Код в ссылке `t.me/бот?start=<код>` для привязки чата мастера.

    Выводится из подписи, а не хранится: код нужен ровно на время нажатия
    «Начать», а лишнее поле в конфигурации пришлось бы ещё и чистить. Короткий
    (16 символов) — Telegram ограничивает параметр `start` 64 символами, и
    ссылка должна оставаться читаемой в сообщении мастеру.
    """
    payload = f"link|{tenant_id}|{master_id}".encode()
    return hmac.new(SIGNING_KEY, payload, hashlib.sha256).hexdigest()[:16]


def user_link_code(user_id: int) -> str:
    """Код в ссылке для привязки Telegram сотруднику панели.

    Бизнес в код не входит: пользователи общие на сервис, а `chat_id` личного
    чата в Telegram — это идентификатор человека, один и тот же для всех ботов.
    """
    return hmac.new(SIGNING_KEY, f"user|{user_id}".encode(), hashlib.sha256).hexdigest()[:16]


def webhook_secret(tenant_id: str) -> str:
    """Секрет вебхука Telegram. Выводится из подписи, а не хранится отдельно."""
    return hmac.new(SIGNING_KEY, f"tg-hook|{tenant_id}".encode(), hashlib.sha256).hexdigest()[:32]


def signed_action(kind: str, tenant_id: str, object_id: str) -> str:
    payload = f"action|{kind}|{tenant_id}|{object_id}".encode()
    return hmac.new(SIGNING_KEY, payload, hashlib.sha256).hexdigest()[:32]


def check_signed_action(token: str, kind: str, tenant_id: str, object_id: str) -> bool:
    return hmac.compare_digest((token or "").encode("utf-8", "ignore"),
                               signed_action(kind, tenant_id, object_id).encode())


def idempotency_key(master_id: str, start_iso: str, phone: str, tenant_id: str = "") -> str:
    digest = hashlib.sha256(
        f"{tenant_id}|{master_id}|{start_iso}|{normalize_phone(phone)}".encode()
    ).hexdigest()
    return digest[:48]


def client_key(phone: str, country_code: str = "") -> str:
    """Ключ клиента по телефону: цифры международного формата, без «+».

    Один и тот же человек набирает номер по-разному: «099 000 101» дома и
    «+598 99 000 101» в переписке. Пока ключом были просто цифры введённого,
    он получал две карточки — и история визитов, неявок и LTV делилась пополам.
    Код страны берётся из настроек салона; не задан — остаются голые цифры.
    """
    return normalize_phone(to_international(phone, country_code)) or normalize_phone(phone)


def client_keys(phone: str, country_code: str = "") -> list[str]:
    """Ключ и его прежние написания — чтобы найти карточку, заведённую до канонизации."""
    keys = [client_key(phone, country_code), normalize_phone(phone)]
    return [k for i, k in enumerate(keys) if k and k not in keys[:i]]


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


# Длины национального номера — только для стран, чей формат мы знаем наверняка.
# Угадывать по коду страны нельзя: аргентинец, набравший домашние «11 2345 6789»
# без плюса, получал бы +598 11234... — уругвайский номер чужого человека.
NATIONAL_LENGTHS: dict[str, tuple[int, ...]] = {
    "598": (8, 9),  # Уругвай: 99 000 102 и 099 000 102
}


def to_international(phone: str, country_code: str = "") -> str:
    """Телефон в E.164: «099 000 101» + «598» → «+59899000101».

    Клиент вводит номер так, как набирает его дома, — с ведущим нулём и без
    кода страны. Twilio такой номер отвергает («is not a valid phone number»),
    и подтверждение не уходит вовсе; в логе это выглядит как проблема Twilio, а
    не как то, что мы отправили мусор.

    Код страны берётся из настроек салона. Пусто — оставляем как есть: угадывать
    страну по длине номера значит однажды отправить сообщение не туда.

    Номер чужой страны код салона не получает. В базе телефон лежит цифрами, без
    «+» (`normalize_phone` его снимает), и функция вызывается ещё раз — уже на
    сохранённом значении: для получателя уведомления, для телефона в сообщении
    мастеру, для ключа карточки. Российские «79991234567» превращались при этом
    в «+59879991234567» — уругвайский номер чужого человека, и сообщение уходило
    ему. Спасает длина: местный номер известной страны такой не бывает, а
    номером без «+» и чужой длины `phone_problem` записаться не даёт вовсе —
    значит цифры уже международные.
    """
    raw = (phone or "").strip()
    digits = normalize_phone(raw)
    if not digits:
        return ""
    if raw.startswith("+"):
        return f"+{digits}"

    code = normalize_phone(country_code)
    if not code:
        return f"+{digits}"
    if digits.startswith(code) and len(digits) > len(code):
        return f"+{digits}"
    # Ведущий ноль — это выход на межгород внутри страны, в E.164 его нет.
    national = digits.lstrip("0")
    lengths = NATIONAL_LENGTHS.get(code)
    if lengths and len(national) not in lengths:
        return f"+{digits}"
    return f"+{code}{national}"


def national_lengths(country_code: str = "") -> tuple[int, ...]:
    """Длины местного номера — виджету, чтобы он проверял ровно то же, что сервер.

    Пока эти длины были вписаны в виджет отдельно, они разошлись: виджет
    пропускал семизначный номер, а сервер отвечал на него отказом уже после
    сводки — и клиенту оставалось только начать сначала.
    """
    return NATIONAL_LENGTHS.get(normalize_phone(country_code), ())


def phone_problem(phone: str, country_code: str = "") -> str:
    """Что с номером не так: «» — всё в порядке.

    Причин ровно две, и путать их нельзя — от них зависит, что клиент увидит.

    ``bad_phone`` — на телефон не похоже вовсе или цифр меньше, чем в местном
    номере. Код страны такому номеру не поможет: он просто неполный, а совет
    «укажите код страны» отправляет клиента искать несуществующую ошибку.

    ``need_country_code`` — цифр столько, что это чужой национальный формат.
    Записаться можно с любого номера мира, но только с кодом страны: без «+»
    такой номер молча стал бы местным номером чужого человека — запись
    создавалась бы, а подтверждение уходило в никуда.
    """
    raw = (phone or "").strip()
    digits = normalize_phone(raw)
    full = normalize_phone(to_international(raw, country_code))
    # E.164 не бывает длиннее пятнадцати цифр, а «1111111111» — не номер:
    # запись по нему создавалась, клиент ничего не получал, а владелец видел
    # живую бронь.
    if not 8 <= len(full) <= 15 or len(set(digits)) <= 1:
        return "bad_phone"
    if raw.startswith("+"):
        return ""

    code = normalize_phone(country_code)
    lengths = NATIONAL_LENGTHS.get(code)
    if not lengths:
        # Страна без известного правила — прежнее поведение, лишний отказ хуже.
        return ""
    # Номер, уже начинающийся с кода страны, ничего не потерял. Именно так он
    # лежит в карточке клиента, и именно в таком виде возвращается оттуда — при
    # записи из листа ожидания и из кабинета. Без этой ветки собственные данные
    # сервиса отвергались как «номер другой страны».
    if digits.startswith(code) and len(digits) - len(code) in lengths:
        return ""
    if len(digits) in lengths:
        return ""
    if len(digits) < min(lengths):
        return "bad_phone"
    return "need_country_code"


def needs_country_code(phone: str, country_code: str = "") -> bool:
    """Номер набран без «+» и длиннее местного — значит код страны потерян."""
    return phone_problem(phone, country_code) == "need_country_code"


def valid_phone(phone: str, country_code: str = "") -> bool:
    """Похоже ли это на телефон, по которому дойдёт сообщение."""
    return not phone_problem(phone, country_code)


def client_confirmed(history: list[dict]) -> bool:
    """Явное согласие ищем в последнем сообщении клиента, а не в словах модели."""
    for msg in reversed(history):
        if msg.get("role") != "user":
            continue
        text = msg.get("content") or ""
        if DECLINE_RE.search(text):
            return False
        return bool(CONFIRM_RE.search(text))
    return False


def mask_pii(text: str) -> str:
    text = PHONE_RE.sub("+***", text or "")
    return EMAIL_RE.sub("***@***", text)


class RateLimiter:
    """Лимит в памяти процесса; при нескольких репликах Coolify нужен Redis."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, per_minute: int) -> bool:
        if per_minute <= 0:
            return True
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= per_minute:
            return False
        hits.append(now)
        return True


class PiiFilter(logging.Filter):
    """Телефоны и email не должны попадать в логи хостинга."""

    def __init__(self, enabled: bool = True) -> None:
        super().__init__()
        self.enabled = enabled

    def filter(self, record: logging.LogRecord) -> bool:
        if self.enabled and isinstance(record.msg, str):
            # Маскируем уже собранное сообщение: телефон чаще приходит аргументом
            # (%s), а не частью шаблона, и правка одного record.msg его не ловит.
            record.msg = mask_pii(record.getMessage())
            record.args = ()
        return True


def install_pii_filter(enabled: bool = True) -> None:
    """Вешает фильтр на корневые хендлеры.

    Фильтр на логгере срабатывает только для записей, созданных этим логгером, —
    сообщения дочерних (`notify`, `worker`) проходили бы мимо. Хендлер видит всё,
    что до него дошло, поэтому маскирование ставим именно туда.
    """
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for handler in root.handlers:
        handler.filters = [f for f in handler.filters if not isinstance(f, PiiFilter)]
        handler.addFilter(PiiFilter(enabled))


def within_daily_limit(count: int, limit: int | None) -> bool:
    return limit is None or count < int(limit)


def format_slot_label(dt: datetime) -> str:
    return dt.strftime("%H:%M")
