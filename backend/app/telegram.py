"""Подключение Telegram-бота владельца салона.

У Telegram нет OAuth для ботов: единственный способ получить доступ — токен от
@BotFather. Зато всё остальное можно не спрашивать. Имя бота узнаётся из
``getMe``, а ``chat_id`` — самое неудобное поле в панели, потому что это число,
которое владелец обычно ищет через сторонних ботов, — вычисляется сам: владелец
пишет боту «/start», сервис читает ``getUpdates`` и берёт чат оттуда.

Входящие обрабатывает :mod:`telegram_bot` через вебхук — там же разбирается и
«/start»: при активной подписке апдейт достаётся вебхуку, а доставленное Telegram
второй раз не отдаёт, поэтому искать его в ``getUpdates`` бесполезно. Функции
чтения ниже остаются запасным путём для бизнесов без вебхука (локальная разработка,
http-адрес): пользоваться ими, пока вебхук активен, Telegram не даёт, и на время
чтения он снимается (``webhook_paused``).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

import httpx

log = logging.getLogger("telegram")

API = "https://api.telegram.org"
TIMEOUT = 10.0


class TelegramError(RuntimeError):
    """Текст безопасно показывать в админке."""


def _call(token: str, method: str, **params) -> dict:
    if not token:
        raise TelegramError("Токен бота не задан")
    try:
        response = httpx.post(f"{API}/bot{token}/{method}", json=params, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise TelegramError(f"Telegram недоступен: {exc}") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if response.status_code == 401 or payload.get("error_code") == 401:
        raise TelegramError("Telegram не принял токен — проверьте, что скопирован он целиком")
    if not payload.get("ok"):
        raise TelegramError(payload.get("description") or f"Telegram ответил {response.status_code}")
    return payload.get("result") or {}


def me(token: str) -> dict:
    """Кто этот бот. Заодно единственная настоящая проверка токена."""
    result = _call(token, "getMe")
    return {"id": result.get("id"), "username": result.get("username") or "",
            "title": result.get("first_name") or ""}


@contextmanager
def webhook_paused(token: str, url: str = "", secret: str = ""):
    """Снимает вебхук на время чтения `getUpdates` и возвращает обратно.

    Telegram не даёт пользоваться `getUpdates`, пока активен вебхук: «Conflict:
    can't use getUpdates method while webhook is active». А привязка чата
    устроена именно на чтении — владелец пишет боту «/start», и мы забираем
    оттуда номер чата.

    Снимаем без `drop_pending_updates`: очередь сохраняется, и то самое
    «/start» дочитывается здесь же. После возврата вебхука Telegram досылает
    накопившееся сам.
    """
    active = ""
    try:
        active = webhook_info(token)["url"]
    except TelegramError:
        pass                      # состояние вебхука не должно ломать привязку
    if active:
        delete_webhook(token)
    try:
        yield
    finally:
        restore = url or active
        if restore and secret:
            try:
                set_webhook(token, restore, secret, drop_pending=False)
            except TelegramError as exc:
                log.error("не удалось вернуть вебхук %s: %s", restore, exc)


def chat_view(chat: dict) -> dict:
    """Чат из апдейта в наш вид: id, человекочитаемое имя, тип.

    Имя Telegram кладёт в разные поля: у группы — `title`, у человека — имя и
    фамилия, у бота-теста бывает только `username`. В панели этот текст стоит
    рядом с номером чата, чтобы владелец узнал, куда именно уйдут уведомления.
    """
    title = chat.get("title") or " ".join(
        p for p in (chat.get("first_name"), chat.get("last_name")) if p
    ) or chat.get("username") or ""
    return {"id": str(chat.get("id") or ""), "title": title, "type": chat.get("type") or ""}


def find_chat(token: str) -> dict | None:
    """Последний чат, из которого боту писали. None — если писем ещё не было.

    Берём именно последнее сообщение: владелец нажимает «Связать чат» сразу
    после «/start», а старые апдейты могут быть из чужого чата, если ботом уже
    пользовались.
    """
    updates = _call(token, "getUpdates", timeout=0, limit=20, allowed_updates=["message"])
    for update in reversed(updates if isinstance(updates, list) else []):
        chat = ((update.get("message") or {}).get("chat")) or {}
        if chat.get("id"):
            return chat_view(chat)
    return None


def find_chat_by_code(token: str, code: str) -> dict | None:
    """Чат, из которого пришёл «/start <код>». None — если такого не было.

    Мастеров несколько, и «последний написавший» их не различает: двое нажали
    «Начать» подряд — и оба уведомления уедут одному. Поэтому у каждого мастера
    своя ссылка `t.me/бот?start=<код>`: Telegram передаёт код первым сообщением,
    и чат сопоставляется с конкретным мастером, а не с временем нажатия.
    """
    if not code:
        return None
    updates = _call(token, "getUpdates", timeout=0, limit=100, allowed_updates=["message"])
    for update in reversed(updates if isinstance(updates, list) else []):
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        if text not in (f"/start {code}", f"/start@{code}", code):
            continue
        chat = message.get("chat") or {}
        if chat.get("id"):
            return chat_view(chat)
    return None


def send(token: str, chat_id: str, text: str, buttons: list[list[dict]] | None = None) -> None:
    """Сообщение в чат. `buttons` — ряды инлайн-кнопок `{text, callback_data}`."""
    params: dict = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    _call(token, "sendMessage", **params)


def answer_callback(token: str, callback_id: str, text: str = "") -> None:
    """Гасит «часики» на нажатой кнопке. Без этого она крутится до таймаута."""
    _call(token, "answerCallbackQuery", callback_query_id=callback_id, text=text)


def edit_markup(token: str, chat_id: str, message_id: int,
                buttons: list[list[dict]] | None = None) -> None:
    """Меняет кнопки под уже отправленным сообщением.

    После «Клиент пришёл» кнопки убираются: иначе тот же выбор можно нажать
    ещё раз, и непонятно, что состояние уже изменилось.
    """
    _call(token, "editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
          reply_markup={"inline_keyboard": buttons or []})


def set_webhook(token: str, url: str, secret: str, drop_pending: bool = True) -> None:
    """Подписывает бота на входящие. `secret` приходит обратно в заголовке.

    Проверять его обязательно: адрес вебхука угадывается, и без подписи любой
    мог бы слать боту команды от чужого имени.

    `drop_pending` выключается при возврате вебхука после паузы: там очередь
    нужно сохранить, иначе нажатия кнопок, сделанные во время привязки чата,
    пропадут молча.
    """
    _call(token, "setWebhook", url=url, secret_token=secret,
          allowed_updates=["message", "callback_query"], drop_pending_updates=drop_pending)


def delete_webhook(token: str) -> None:
    _call(token, "deleteWebhook", drop_pending_updates=False)


def webhook_info(token: str) -> dict:
    info = _call(token, "getWebhookInfo")
    return {"url": info.get("url") or "", "pending": info.get("pending_update_count") or 0,
            "error": info.get("last_error_message") or ""}
