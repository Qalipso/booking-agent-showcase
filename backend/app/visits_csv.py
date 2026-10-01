"""Импорт истории визитов из CSV.

База клиентов без истории — это список телефонов: сегменты пустые, LTV нулевой,
возвращаемость неизвестна, и всё, чем платный YCLIENTS отличается от бесплатного
DIKIDI, включается у переехавшего салона через год. С историей — в день переезда.

Два правила, ради которых этот модуль отдельный, а не ветка в записи:

**Ни одного события в календаре и ни одной задачи в очереди.** Импорт идёт мимо
``BookingTools.create_booking``: тот подтверждает слот, пишет в Google Calendar и
планирует напоминания. На прошлогодних визитах это означало бы рассылку «напоминаем:
завтра в 15:00» по всей базе в день переезда — худшее, что может случиться с салоном.
Записи создаются прямо через ``Store.create_booking`` со ``source = "import"`` и
``notify_consent = False``.

**Время визита обязательно.** Без него вся история мастера падает на одну минуту,
упирается в уникальный индекс слота и отклоняется целиком. Дата без времени — не
история, а список дат.

Разбор терпим к чужому файлу так же, как ``clients_csv``: «;» вместо «,», BOM,
названия колонок и статусов на трёх языках, деньги в любом написании.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, timedelta, timezone

from sqlalchemy import select

from .db import Booking, SlotTaken
from .policies import client_key, client_keys, needs_country_code, normalize_phone, valid_phone
from .timeutil import norm_lang, zoned

COLUMNS: dict[str, tuple[str, ...]] = {
    "phone": ("phone", "телефон", "тел", "номер", "teléfono", "telefono", "celular", "mobile"),
    "name": ("name", "имя", "фио", "клиент", "nombre", "cliente", "client"),
    "date": ("date", "дата", "дата визита", "fecha"),
    "time": ("time", "время", "hora"),
    "service": ("service", "услуга", "сервис", "servicio"),
    "master": ("master", "мастер", "сотрудник", "специалист", "staff", "employee",
               "profesional", "especialista"),
    "amount": ("amount", "сумма", "стоимость", "цена", "оплачено", "итого",
               "price", "total", "importe", "monto"),
    "status": ("status", "статус", "estado"),
    "comment": ("comment", "комментарий", "примечание", "заметка", "comentario"),
}

# Статусы приходят словами живого языка, а не нашими кодами.
STATUSES: dict[str, tuple[str, ...]] = {
    "completed": ("completed", "выполнена", "выполнен", "завершена", "завершён", "завершен",
                  "пришёл", "пришел", "оказана", "done", "atendido", "completado", "finalizado"),
    "no_show": ("no_show", "no show", "неявка", "не пришёл", "не пришел", "noshow", "ausente"),
    "cancelled": ("cancelled", "canceled", "отменена", "отменён", "отменен", "отмена",
                  "cancelado", "anulado"),
}
STATUS_INDEX = {word: code for code, words in STATUSES.items() for word in words}

DEFAULT_DURATION = 60
PREVIEW_LIMIT = 500


@dataclass
class Row:
    """Разобранная строка файла — то, что панель показывает в предпросмотре."""

    line: int
    phone: str = ""
    name: str = ""
    when: str = ""
    service: str = ""
    master: str = ""
    action: str = "created"          # created | rejected
    reason: str = ""
    values: dict = field(default_factory=dict)
    start: object = None             # datetime в поясе салона
    minutes: int = DEFAULT_DURATION
    service_id: str = ""
    master_id: str = ""
    status: str = "completed"
    amount: int = 0

    def as_dict(self) -> dict:
        return {"line": self.line, "phone": self.phone, "name": self.name,
                "when": self.when, "service": self.service, "master": self.master,
                "action": self.action, "reason": self.reason}


def _dialect(text: str) -> str:
    head = text.splitlines()[0] if text.splitlines() else ""
    return ";" if head.count(";") > head.count(",") else ","


def _map_header(fieldnames: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for raw in fieldnames or []:
        key = (raw or "").strip().lstrip("﻿").lower()
        for field_name, variants in COLUMNS.items():
            if key in variants:
                mapping[raw] = field_name
                break
    return mapping


def _date(value: str) -> str:
    """Дата в любом из трёх написаний → ``YYYY-MM-DD``. Пусто, если не дата.

    День первым: так пишут и в России, и в Уругвае. Американский файл выдаёт
    себя сам — если первое число не больше двенадцати, а второе больше, порядок
    меняем. Полностью неоднозначное «03/04» остаётся третьим апреля.
    """
    text = str(value or "").strip()
    iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if iso:
        year, month, day = (int(x) for x in iso.groups())
    else:
        parts = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})$", text)
        if not parts:
            return ""
        day, month, year = (int(x) for x in parts.groups())
        if day <= 12 < month:
            day, month = month, day
        if year < 100:
            year += 2000
    if not 2000 <= year <= 2100:
        return ""
    try:
        # Календарь проверяем здесь: «31.02» дальше упёрлось бы в zoned() и
        # уронило весь импорт пятисоткой вместо одной отклонённой строки.
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _time(value: str) -> str:
    match = re.match(r"^(\d{1,2}):(\d{2})", str(value or "").strip())
    if not match:
        return ""
    hour, minute = int(match.group(1)), int(match.group(2))
    return f"{hour:02d}:{minute:02d}" if hour < 24 and minute < 60 else ""


def _money(value: str) -> int:
    """«$ 1.200,50», «1 200», «900 UYU» → целое.

    Дробная часть отбрасывается: суммы в базе целые, и сентаво в истории визитов
    не стоят того, чтобы менять тип колонки.
    """
    text = re.sub(r"[^\d.,]", "", str(value or ""))
    if not text:
        return 0
    separator = max(text.rfind(","), text.rfind("."))
    # Один-два знака после последнего разделителя — это дробная часть,
    # три — разделитель тысяч («1.200» — тысяча двести, а не один и два).
    whole = text[:separator] if separator != -1 and len(text) - separator - 1 in (1, 2) else text
    digits = re.sub(r"\D", "", whole)
    return int(digits) if digits else 0


def _pick(catalogue: list[dict], text: str, *, keys: tuple[str, ...]) -> dict | None:
    needle = str(text or "").strip().lower()
    if not needle:
        return None
    for item in catalogue:
        names = {str(item.get(key, "")).strip().lower() for key in keys if item.get(key)}
        if needle in names:
            return item
    return None


def parse(text: str, *, tenant, country: str = "") -> tuple[list[Row], list[str]]:
    """Разбирает файл. Возвращает строки и список колонок, которых не хватило."""
    text = (text or "").lstrip("﻿")
    if not text.strip():
        return [], ["phone", "date", "time"]

    reader = csv.DictReader(io.StringIO(text), delimiter=_dialect(text))
    mapping = _map_header(list(reader.fieldnames or []))
    present = set(mapping.values())

    services, masters = tenant.services, tenant.masters
    missing = [name for name in ("phone", "date", "time") if name not in present]
    # Услугу и мастера можно не называть там, где выбора нет: у соло-мастера
    # колонка «мастер» в выгрузке отсутствует как ненужная.
    if "service" not in present and len(services) != 1:
        missing.append("service")
    if "master" not in present and len(masters) != 1:
        missing.append("master")
    if missing:
        return [], missing

    rows: list[Row] = []
    seen: set[tuple[str, str]] = set()
    for number, raw in enumerate(reader, start=2):
        values = {field_name: str(raw.get(column) or "").strip()
                  for column, field_name in mapping.items()}
        if not any(values.values()):
            continue

        row = Row(line=number, phone=values.get("phone", ""), name=values.get("name", ""),
                  service=values.get("service", ""), master=values.get("master", ""),
                  values=values)
        rows.append(row)

        phone_raw = values.get("phone", "")
        if not normalize_phone(phone_raw):
            row.action, row.reason = "rejected", "нет телефона"
            continue
        if (len(normalize_phone(phone_raw)) < 7 or needs_country_code(phone_raw, country)
                or not valid_phone(phone_raw, country)):
            row.action, row.reason = "rejected", "телефон не похож на настоящий"
            continue
        row.phone = client_key(phone_raw, country)

        date_key, time_key = _date(values.get("date", "")), _time(values.get("time", ""))
        if not date_key:
            row.action, row.reason = "rejected", "не разобрали дату"
            continue
        if not time_key:
            row.action, row.reason = "rejected", "не разобрали время визита"
            continue
        row.when = f"{date_key} {time_key}"

        service = _pick(services, values.get("service", ""),
                        keys=("id", "title", "titleEs", "titleEn")) or (
            services[0] if "service" not in present else None)
        if not service:
            row.action, row.reason = "rejected", f"услуга не найдена: {values.get('service', '')}"
            continue
        master = _pick(masters, values.get("master", ""), keys=("id", "name")) or (
            masters[0] if "master" not in present else None)
        if not master:
            row.action, row.reason = "rejected", f"мастер не найден: {values.get('master', '')}"
            continue

        row.service_id, row.master_id = service["id"], master["id"]
        row.minutes = int(service.get("duration") or DEFAULT_DURATION)
        row.start = zoned(date_key, time_key, tenant.timezone)
        row.status = STATUS_INDEX.get(values.get("status", "").strip().lower(), "completed")
        row.amount = _money(values.get("amount", ""))

        # Дубль внутри файла: та же минута у того же мастера. Ловим здесь, а не
        # уникальным индексом, чтобы причина в отчёте была человеческой.
        key = (row.master_id, row.start.isoformat())
        if key in seen:
            row.action, row.reason = "rejected", "это время уже есть в файле"
            continue
        seen.add(key)
    return rows, []


def unmatched(rows: list[Row]) -> dict[str, list[str]]:
    """Названия, которые не нашлись в справочниках, — их сопоставляют руками."""
    out = {"services": [], "masters": []}
    for row in rows:
        if row.reason.startswith("услуга не найдена") and row.service not in out["services"]:
            out["services"].append(row.service)
        if row.reason.startswith("мастер не найден") and row.master not in out["masters"]:
            out["masters"].append(row.master)
    return out


def _utc_key(value) -> str:
    """Время визита в сравнимом виде. SQLite отдаёт naive-время, и это UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _already_imported(store, rows: list[Row], *, tenant_id: str) -> set[tuple[str, str, str]]:
    """Визиты, которые в базе уже есть: мастер, услуга и минута начала.

    Уникального индекса для этого мало: слот держат только подтверждённые и
    состоявшиеся записи, а история состоит ещё и из неявок с отменами — второй
    заход тем же файлом их бы удвоил.
    """
    starts = [row.start for row in rows if row.action != "rejected" and row.start]
    if not starts:
        return set()
    # Границы — в UTC: время в базе хранится в UTC, а SQLite при сравнении
    # игнорирует пояс у параметра. С границей в поясе салона последний визит дня
    # выпадал из выборки, и повторный импорт заводил его второй раз.
    low, high = min(starts).astimezone(timezone.utc), max(starts).astimezone(timezone.utc)
    with store.session_factory() as session:
        found = session.scalars(select(Booking).where(
            Booking.tenant_id == tenant_id,
            Booking.start_at >= low, Booking.start_at <= high)).all()
    return {(b.master_id, b.service_id, _utc_key(b.start_at)) for b in found}


def apply(store, rows: list[Row], *, tenant, country: str, commit: bool) -> dict:
    """Считает, что произойдёт, и — если ``commit`` — создаёт записи."""
    created = 0
    touched: set[str] = set()
    lang = norm_lang(tenant.ai.get("language") or "ru")
    currency = tenant.salon.get("currency") or "UYU"
    known = _already_imported(store, rows, tenant_id=tenant.slug)

    for row in rows:
        if row.action == "rejected":
            continue
        key = (row.master_id, row.service_id, _utc_key(row.start))
        if key in known:
            # Повторный заход тем же файлом ничего не удваивает — и видно это
            # уже в предпросмотре, до всякой записи.
            row.action, row.reason = "rejected", "такой визит уже есть в базе"
            continue
        known.add(key)
        if not commit:
            created += 1
            continue

        client = store.upsert_client(
            tenant_id=tenant.slug, phone=row.phone, name=row.name, lang=lang,
            aliases=client_keys(row.values.get("phone", ""), country))
        service = tenant.service(row.service_id) or {}
        try:
            store.create_booking(
                tenant_id=tenant.slug, client_id=client.id,
                master_id=row.master_id, service_id=row.service_id,
                start_at=row.start, end_at=row.start + timedelta(minutes=row.minutes),
                client_name=row.name or client.name, phone=row.phone, lang=lang,
                source="import", status=row.status,
                comment=row.values.get("comment", ""),
                price_amount=row.amount or int(service.get("priceAmount") or 0),
                paid_amount=row.amount if row.status == "completed" else 0,
                currency=service.get("currency") or currency,
                # Ни одно сообщение по импортированному визиту не уйдёт: очередь
                # мы не трогаем вовсе, но и согласие на всякий случай не ставим.
                notify_consent=False,
            )
        except SlotTaken:
            # Не дубль импорта (его сняли выше), а настоящее пересечение:
            # в эту минуту у мастера уже стоит другая запись.
            row.action = "rejected"
            row.reason = "в это время у мастера уже есть другая запись"
            continue
        created += 1
        touched.add(client.id)

    if commit and touched:
        _refresh_metrics(store, touched)

    rejected = [r for r in rows if r.action == "rejected"]
    shown = sorted(rows, key=lambda r: (r.action != "rejected", r.line))[:PREVIEW_LIMIT]
    return {
        "total": len(rows), "created": created, "rejected": len(rejected),
        "committed": commit, "unmatched": unmatched(rows),
        "rows": [r.as_dict() for r in shown],
        "truncated": max(0, len(rows) - len(shown)),
    }


def _refresh_metrics(store, client_ids: set[str]) -> None:
    """Пересчёт визитов, неявок и LTV после импорта.

    Обычно метрики обновляет смена статуса записи, но импорт создаёт их сразу
    завершёнными. Считаем тем же кодом, что и всё остальное: свой дубль формулы
    LTV разошёлся бы с основным при первой же правке.
    """
    with store.session_factory() as session:
        for client_id in client_ids:
            store._refresh_client_metrics(session, client_id)   # noqa: SLF001
        session.commit()
