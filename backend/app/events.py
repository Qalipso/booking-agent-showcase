"""События бизнеса одной строкой — то, что потом ищут в сборщике логов.

Обычные `log.error("Календарь недоступен: %s", exc)` хороши, когда человек
читает лог глазами. Но на вопрос «сколько записей сорвалось вчера и почему»
свободный текст не отвечает: его нельзя ни отфильтровать, ни сложить в график.

Поэтому ключевые действия пишутся вторым, машинным потоком в формате logfmt:

    event=booking.refused tenant=demo-salon code=daily_limit master=marat

Формат выбран за то, что его одинаково понимают и человек в `docker logs`, и
Loki, Vector, Axiom — без парсера на регулярках. JSON читался бы хуже глазами,
а в терминале лог смотрят чаще, чем в дашборде.

Телефоны и имена сюда не кладём: они всё равно затираются фильтром ПДн
(`policies.install_pii_filter`), но лучше не отправлять наружу то, что потом
придётся замазывать. Клиент опознаётся идентификатором карточки.
"""

from __future__ import annotations

import logging

log = logging.getLogger("event")

# Значения без кавычек, если в них нет пробелов, — иначе logfmt требует кавычек.
_QUOTE = (" ", "=", '"')


def _fmt(value: object) -> str:
    text = "—" if value is None else str(value)
    if any(ch in text for ch in _QUOTE):
        return '"' + text.replace('"', "'") + '"'
    return text


def event(name: str, **fields: object) -> None:
    """Пишет событие. Пустые поля опускаются, чтобы строка не заросла прочерками."""
    parts = [f"event={name}"]
    parts += [f"{key}={_fmt(value)}" for key, value in fields.items() if value not in (None, "")]
    log.info(" ".join(parts))
