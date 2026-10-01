"""Входящие Telegram: команды и кнопки под уведомлениями.

Бот был односторонним — только рассылал записи. Мастеру этого мало: увидев
уведомление, он хочет тут же отметить, что клиент пришёл, а утром — посмотреть
свой день, не открывая панель.

Кто пишет, определяется по `chat_id`: он же лежит в карточке мастера и в
профиле сотрудника. Мастер видит только свои записи, сотрудник — все. Незнакомый
чат не получает ничего: бот салона не должен отвечать посторонним.
"""

from __future__ import annotations

import hmac
import json
import logging
from datetime import datetime, timedelta, timezone

from . import auth, telegram
from .db import BOOKING_STATUSES
from .policies import master_link_code, user_link_code
from .tenants import Tenant
from .timeutil import human_date, now, today_key, zoned

log = logging.getLogger("telegram.bot")

HELP = (
    "Это бот салона {salon}. Сюда приходят новые записи и отмены.\n\n"
    "Команды:\n"
    "/today — записи на сегодня\n"
    "/tomorrow — записи на завтра\n\n"
    "Под каждым уведомлением есть кнопки: отметить визит или отменить запись."
)

WELCOME_MASTER = ("{salon}: готово, {name}. Сюда будут приходить ваши записи.\n\n"
                  "/today — записи на сегодня, /tomorrow — на завтра.")
WELCOME_STAFF = ("{salon}: готово. Сюда будут приходить новые записи салона.\n\n"
                 "/today — записи на сегодня, /tomorrow — на завтра.")

# Чат, из которого боту написали «/start» без кода, — кандидат на привязку
# владельцу. Хранится в `tenant_secrets`: другого хранилища «ключ-значение по
# бизнесу» в сервисе нет, а пережить перезапуск запись обязана — «Связать чат»
# в панели нажимают минутой позже. Наружу этот ключ не отдаётся: форма показывает
# только пути из `secretstore.SECRET_PATHS`.
PENDING_CHAT_KEY = "telegram.pendingChat"
# Час: за это время владелец успевает вернуться в панель, а вчерашнее «/start»
# случайного человека уже не станет адресом уведомлений салона.
PENDING_TTL = timedelta(hours=1)

# Подписи статусов в кнопках. «Отменить» стоит последней и отделена: её
# последствия необратимы, и рядом с «пришёл» её нажимают по инерции.
ACTIONS = [
    ("completed", "✓ Пришёл"),
    ("no_show", "✕ Не пришёл"),
    ("cancelled", "Отменить запись"),
]


def booking_buttons(booking_id: str) -> list[list[dict]]:
    first = [{"text": label, "callback_data": f"b:{status}:{booking_id}"}
             for status, label in ACTIONS[:2]]
    last = [{"text": ACTIONS[2][1], "callback_data": f"b:{ACTIONS[2][0]}:{booking_id}"}]
    payment = [
        {"text": "💵 Оплачено наличными", "callback_data": f"p:cash:{booking_id}"},
        {"text": "💳 Оплачено картой", "callback_data": f"p:card:{booking_id}"},
    ]
    return [first, payment, last]


def whois(tenant: Tenant, store, chat_id: str) -> dict | None:
    """Мастер, сотрудник или никто. Незнакомому чату бот не отвечает."""
    chat_id = str(chat_id or "").strip()
    if not chat_id:
        return None
    for master in tenant.masters:
        if str(master.get("telegramChatId") or "").strip() == chat_id:
            return {"kind": "master", "id": master["id"], "name": master.get("name") or master["id"]}
    for person in store.staff_recipients():
        if str(person["chatId"]).strip() == chat_id:
            return {"kind": "staff", "id": person["id"], "name": person["name"]}
    return None


def remember_start(store, tenant_id: str, chat: dict) -> None:
    """Запоминает чат, из которого написали «/start», — для кнопки в панели."""
    store.set_secret(tenant_id, PENDING_CHAT_KEY,
                     json.dumps({**chat, "at": datetime.now(timezone.utc).isoformat()}))


def pending_chat(store, tenant_id: str) -> dict | None:
    """Кто последним написал боту «/start». None — если никто или запись стара."""
    raw = store.get_secret(tenant_id, PENDING_CHAT_KEY)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        written = datetime.fromisoformat(data["at"])
    except (ValueError, KeyError, TypeError):
        return None
    if datetime.now(timezone.utc) - written > PENDING_TTL or not data.get("id"):
        return None
    return {"id": str(data["id"]), "title": data.get("title") or "", "type": data.get("type") or ""}


def forget_start(store, tenant_id: str) -> None:
    """После привязки кандидат больше не нужен — иначе привяжется ещё раз."""
    store.set_secret(tenant_id, PENDING_CHAT_KEY, "")


def _same_code(given: str, expected: str) -> bool:
    # Код приходит из сообщения, то есть может быть чем угодно: compare_digest
    # не принимает не-ASCII строки, поэтому сравниваем байты.
    return hmac.compare_digest(given.encode("utf-8", "ignore"), expected.encode())


def _bind_master(tenant: Tenant, master_id: str, chat_id: str) -> None:
    """Записывает чат мастера в salon.json.

    Пересобирать сервисы бизнеса не нужно: реестр отдаёт тот же объект `Tenant`,
    который правит `patch_salon`, — уведомления увидят новый чат сразу.
    """
    masters = [dict(m) for m in tenant.salon.get("masters") or []]
    for m in masters:
        if m.get("id") == master_id:
            m["telegramChatId"] = chat_id
    tenant.patch_salon({"masters": masters})


def _handle_start(chat: dict, code: str, tenant: Tenant, store, token: str) -> str:
    """«/start» и «/start <код>» — привязка чата, а не просто приветствие.

    Раньше это делала панель через `getUpdates`, но с активным вебхуком апдейт
    достаётся вебхуку: доставленное Telegram второй раз не отдаёт. Поэтому код
    из ссылки `t.me/бот?start=<код>` разбирается здесь же, и мастер оказывается
    подключён в тот момент, когда нажал «Начать», — без похода в панель.
    """
    view = telegram.chat_view(chat)
    chat_id = view["id"]
    salon = tenant.salon.get("name") or tenant.slug

    if code:
        master = next((m for m in tenant.masters
                       if _same_code(code, master_link_code(tenant.slug, m["id"]))), None)
        if master:
            _bind_master(tenant, master["id"], chat_id)
            telegram.send(token, chat_id, WELCOME_MASTER.format(
                salon=salon, name=master.get("name") or master["id"]))
            return f"мастер {master['id']} привязан к чату {chat_id}"

        user = next((u for u in auth.list_users(store)
                     if _same_code(code, user_link_code(u.id))), None)
        if user:
            auth.update_user(store, user.id, telegram_chat_id=chat_id)
            telegram.send(token, chat_id, WELCOME_STAFF.format(salon=salon))
            return f"сотрудник {user.id} привязан к чату {chat_id}"

        # Код не наш: ссылка другого салона или сгенерированная до смены ключа
        # подписи. Молчим и обрабатываем как обычный «/start».
        log.info("[%s] код привязки не подошёл", tenant.slug)

    who = whois(tenant, store, chat_id)
    if who:
        telegram.send(token, chat_id, HELP.format(salon=salon))
        return f"{who['kind']} {who['name']}: /start"

    # Чат ещё не привязан — запоминаем, дальше владелец нажмёт «Связать чат».
    # Молча: ответ незнакомцу подтверждал бы, что бот живой и чей он.
    remember_start(store, tenant.slug, view)
    return f"чат {chat_id} ждёт привязки"


def day_report(tenant: Tenant, store, who: dict, date_str: str) -> str:
    """Список записей на день — то, ради чего мастер открывал бы панель."""
    tz = tenant.timezone
    start = zoned(date_str, "00:00", tz)
    rows = store.day_bookings(tenant_id=tenant.slug, start=start, end=start + timedelta(days=1))
    if who["kind"] == "master":
        rows = [b for b in rows if b.master_id == who["id"]]
    rows = [b for b in rows if b.status != "cancelled"]

    label = human_date(date_str)
    if not rows:
        return f"{label}: записей нет."

    lines = [f"{label}:"]
    for b in sorted(rows, key=lambda x: x.start_at):
        service = (tenant.service(b.service_id) or {}).get("title", b.service_id)
        master = (tenant.master(b.master_id) or {}).get("name", b.master_id)
        when = b.start_at.astimezone(start.tzinfo).strftime("%H:%M")
        who_line = f" · {master}" if who["kind"] == "staff" else ""
        mark = {"completed": " ✓", "no_show": " ✕"}.get(b.status, "")
        lines.append(f"{when} — {service}{who_line} · {b.client_name}, {b.phone}{mark}")
    return "\n".join(lines)


def handle_update(update: dict, tenant: Tenant, store, token: str) -> str:
    """Один апдейт от Telegram. Возвращает краткое описание для лога."""
    if "callback_query" in update:
        return _handle_callback(update["callback_query"], tenant, store, token)
    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if not (text and chat_id):
        return "пропущено"

    parts = text.split()
    command = parts[0].lower().lstrip("/").split("@")[0]
    # «/start» разбирается до проверки «свой ли чат»: именно им незнакомый чат и
    # становится своим.
    if command == "start":
        return _handle_start(chat, parts[1] if len(parts) > 1 else "", tenant, store, token)

    who = whois(tenant, store, chat_id)
    if not who:
        # Молчим: это либо посторонний, либо человек, которого ещё не привязали.
        # Отвечать «вы не сотрудник» — рассказывать чужим о существовании салона.
        return f"чужой чат {chat_id}"

    if command in ("today", "сегодня"):
        body = day_report(tenant, store, who, today_key(tenant.timezone))
    elif command in ("tomorrow", "завтра"):
        tomorrow = (now(tenant.timezone) + timedelta(days=1)).date().isoformat()
        body = day_report(tenant, store, who, tomorrow)
    else:
        body = HELP.format(salon=tenant.salon.get("name") or tenant.slug)

    telegram.send(token, chat_id, body)
    return f"{who['kind']} {who['name']}: /{command}"


def _handle_callback(query: dict, tenant: Tenant, store, token: str) -> str:
    data = (query.get("data") or "").split(":")
    message = query.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id") or "")
    callback_id = query.get("id") or ""

    who = whois(tenant, store, chat_id)
    if not who or len(data) != 3 or data[0] not in ("b", "p"):
        telegram.answer_callback(token, callback_id, "Не могу это выполнить")
        return "чужой или непонятный колбэк"

    action, status, booking_id = data
    if action == "p" and status not in ("cash", "card"):
        telegram.answer_callback(token, callback_id, "Неизвестный способ оплаты")
        return f"неизвестная оплата {status}"
    if action == "b" and status not in BOOKING_STATUSES:
        telegram.answer_callback(token, callback_id, "Неизвестное действие")
        return f"неизвестный статус {status}"

    booking = store.get_booking(booking_id, tenant_id=tenant.slug)
    if not booking:
        telegram.answer_callback(token, callback_id, "Запись не найдена")
        return "запись не найдена"
    # Мастер распоряжается только своими записями, даже зная чужой id.
    if who["kind"] == "master" and booking.master_id != who["id"]:
        telegram.answer_callback(token, callback_id, "Это запись другого мастера")
        return "чужая запись"

    if action == "p":
        amount = max(0, int(booking.price_amount or 0) - int(booking.discount_amount or 0))
        store.set_payment(booking_id, tenant_id=tenant.slug, paid_amount=amount,
                          payment_method=status, discount_amount=booking.discount_amount)
        said = f"Оплата отмечена: {amount} {booking.currency}, {status}"
        telegram.answer_callback(token, callback_id, said)
        telegram.send(token, chat_id, f"{said}: {booking.client_name}.")
        return f"{who['name']} → paid {booking_id[:8]}"

    store.set_booking_status(booking_id, status, tenant_id=tenant.slug)
    if status in ("completed", "cancelled"):
        from .notify.service import NotificationService
        notifications = NotificationService(store)
        if status == "completed":
            notifications.schedule_review(booking, tenant)
            if booking.client_id and tenant.salon.get("loyaltyEnabled"):
                percent = max(0, int(tenant.salon.get("loyaltyPercent") or 0))
                points = int(booking.paid_amount or 0) * percent // 100
                if points:
                    store.change_loyalty(
                        tenant_id=tenant.slug, client_id=booking.client_id, points=points,
                        reason="Кэшбэк за визит", booking_id=booking.id, idempotent=True)
        else:
            # Мастер нажал «Отменить» — снимаем напоминания, говорим клиенту и
            # только потом предлагаем окно листу ожидания.
            notifications.cancel_for_booking(booking.id, "cancelled_by_master")
            notifications.notify_client_cancelled(booking, tenant)
            notifications.offer_waitlist(booking, tenant)
    said = {"completed": "Отмечено: клиент пришёл",
            "no_show": "Отмечено: не пришёл",
            "cancelled": "Запись отменена"}[status]
    telegram.answer_callback(token, callback_id, said)
    # Кнопки убираем: состояние уже изменилось, повторный выбор бессмыслен.
    if message.get("message_id"):
        try:
            telegram.edit_markup(token, chat_id, message["message_id"])
        except telegram.TelegramError as exc:
            log.warning("не удалось убрать кнопки: %s", exc)
    telegram.send(token, chat_id, f"{said}: {booking.client_name}.")
    return f"{who['name']} → {status} {booking_id[:8]}"
