"""Даты в таймзоне салона. Все внутренние расчёты — в aware-datetime."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# Форматы дат и времени на границе API. Те же строки уходят в схемы запросов,
# чтобы кривой ввод отсекался до бизнес-логики и с указанием поля.
DATE_PATTERN = r"\d{4}-\d{2}-\d{2}"
TIME_PATTERN = r"([01]\d|2[0-3]):[0-5]\d"


class BadDate(ValueError):
    """Дата или время не разобраны. Текст безопасно показывать клиенту.

    Отдельный тип, потому что снаружи это ошибка запроса, а не сбой сервиса:
    голый ValueError из `date.fromisoformat` долетал до обработчика ASGI и
    превращался в 500 — виджет получал «Internal Server Error», а в логи падал
    трейс, неотличимый от настоящей поломки.
    """

# Подписи дат для языков виджета. Язык приходит из запроса, ru — запасной.
DAYS = {
    "ru": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
    "es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}
MONTHS = {
    "ru": ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"],
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}
TODAY_LABEL = {"ru": "сегодня", "es": "hoy", "en": "today"}
RU_DAYS = DAYS["ru"]      # исторические алиасы
RU_MONTHS = MONTHS["ru"]


def norm_lang(lang: str | None) -> str:
    code = (lang or "").strip().lower()[:2]
    return code if code in DAYS else "ru"


def tz(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def now(tz_name: str) -> datetime:
    return datetime.now(tz(tz_name))


def parse_date(date_str: str) -> date:
    """'2026-08-10' → date. Всё остальное — понятная ошибка запроса."""
    try:
        return date.fromisoformat((date_str or "").strip())
    except (TypeError, ValueError) as exc:
        raise BadDate(f"Дата «{date_str}» непонятна — нужен формат 2026-08-10") from exc


def parse_time(value: str) -> tuple[int, int]:
    """'11:00' → (11, 0). Проверяем и формат, и диапазон."""
    if not re.fullmatch(TIME_PATTERN, (value or "").strip()):
        raise BadDate(f"Время «{value}» непонятно — нужен формат 11:00")
    hh, mm = (int(x) for x in value.strip().split(":"))
    return hh, mm


def zoned(date_str: str, time_str: str, tz_name: str) -> datetime:
    """'2026-08-10' + '11:00' в зоне салона → aware datetime."""
    d = parse_date(date_str)
    hh, mm = parse_time(time_str)
    return datetime.combine(d, time(hh, mm), tzinfo=tz(tz_name))


def utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)


def utc_iso(value: datetime | None) -> str | None:
    """ISO с указанием пояса. Наивное время считаем UTC — так его пишет база.

    Без пояса браузер принимает время за своё местное: панель показывала визит
    на три часа позже, ровно на разницу Монтевидео с UTC.
    """
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def weekday_of(date_str: str) -> int:
    """0 = воскресенье — как в конфиге и в Google Calendar."""
    return (parse_date(date_str).weekday() + 1) % 7


def human_date(date_str: str, lang: str = "ru") -> str:
    d = parse_date(date_str)
    code = norm_lang(lang)
    day, month = DAYS[code][d.weekday()], MONTHS[code][d.month - 1]
    if code == "en":
        return f"{day}, {month} {d.day}"
    return f"{day}, {d.day} {month}"


def today_key(tz_name: str) -> str:
    return now(tz_name).date().isoformat()


def date_keys(tz_name: str, days: int) -> list[str]:
    start = now(tz_name).date()
    return [(start + timedelta(days=i)).isoformat() for i in range(days)]


def minutes_of(time_str: str) -> int:
    hh, mm = parse_time(time_str)
    return hh * 60 + mm


def time_str(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
