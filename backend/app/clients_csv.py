"""Импорт и экспорт клиентской базы в CSV.

Салон, который сидит в DIKIDI или YCLIENTS, переезжает вместе с базой клиентов
или не переезжает вовсе — выгрузка в Excel есть у обоих. Поэтому разбор здесь
терпимый к чужим файлам: точка с запятой вместо запятой (так Excel сохраняет
в русской и испанской локали), BOM в начале, свои названия колонок на трёх
языках, телефон в любом написании.

Терпимость кончается на телефоне: он и есть ключ карточки. Строка без внятного
номера отклоняется с причиной, а не заводит клиента, которому нельзя написать.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from .policies import client_key, client_keys, needs_country_code, normalize_phone, valid_phone
from .timeutil import norm_lang

# Названия колонок, которые встречаются в выгрузках: наши, русские, испанские,
# английские. Ключ — наше поле, значения — то, что может стоять в шапке файла.
COLUMNS: dict[str, tuple[str, ...]] = {
    "name": ("name", "имя", "фио", "клиент", "nombre", "cliente", "client", "full name"),
    "phone": ("phone", "телефон", "тел", "номер", "teléfono", "telefono", "celular", "mobile"),
    "lang": ("lang", "язык", "idioma", "language"),
    "notes": ("notes", "заметки", "комментарий", "примечание", "notas", "comment", "comments"),
    "tags": ("tags", "теги", "метки", "etiquetas"),
    "consent": ("consent", "согласие", "рассылка", "consentimiento", "marketing"),
    "blocked": ("blocked", "чёрный список", "черный список", "блокирован", "bloqueado"),
}

EXPORT_HEADER = ("name", "phone", "lang", "notes", "tags", "consent", "blocked",
                 "visits", "no_shows", "ltv", "loyalty", "first_seen", "last_visit")

PREVIEW_LIMIT = 500   # строк в отчёте; счётчики считаются по всему файлу

_TRUE = {"1", "да", "true", "yes", "y", "sí", "si", "+"}
_FALSE = {"0", "нет", "false", "no", "n", "-", ""}


@dataclass
class Row:
    """Одна разобранная строка файла — то, что панель показывает в предпросмотре."""

    line: int
    name: str = ""
    phone: str = ""
    action: str = "created"          # created | updated | rejected
    reason: str = ""
    values: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"line": self.line, "name": self.name, "phone": self.phone,
                "action": self.action, "reason": self.reason}


def _flag(value: str, default: bool) -> bool:
    text = str(value or "").strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False if text else default
    return default


def _dialect(text: str) -> str:
    """Разделитель: запятая или точка с запятой. Excel в ru/es пишет вторую."""
    head = text.splitlines()[0] if text.splitlines() else ""
    return ";" if head.count(";") > head.count(",") else ","


def _map_header(fieldnames: list[str]) -> dict[str, str]:
    """Колонка файла → наше поле. Незнакомые колонки просто игнорируются."""
    mapping: dict[str, str] = {}
    for raw in fieldnames or []:
        key = (raw or "").strip().lstrip("﻿").lower()
        for field_name, variants in COLUMNS.items():
            if key in variants:
                mapping[raw] = field_name
                break
    return mapping


def parse(text: str, *, country: str = "") -> tuple[list[Row], list[str]]:
    """Разбирает файл. Возвращает строки и список колонок, которых не хватило."""
    text = (text or "").lstrip("﻿")
    if not text.strip():
        return [], ["phone"]

    reader = csv.DictReader(io.StringIO(text), delimiter=_dialect(text))
    mapping = _map_header(list(reader.fieldnames or []))
    if "phone" not in mapping.values():
        return [], ["phone"]

    rows: list[Row] = []
    seen: set[str] = set()
    for number, raw in enumerate(reader, start=2):   # первая строка — шапка
        values = {field_name: str(raw.get(column) or "").strip()
                  for column, field_name in mapping.items()}
        phone_raw = values.get("phone", "")
        row = Row(line=number, name=values.get("name", ""), phone=phone_raw, values=values)

        if not any(values.values()):
            continue   # пустая строка в конце файла — не ошибка
        # Пустая ячейка и кривой номер — разные беды, и чинят их по-разному:
        # в первом случае номер ищут, во втором исправляют.
        if not normalize_phone(phone_raw):
            row.action, row.reason = "rejected", "нет телефона"
        elif (len(normalize_phone(phone_raw)) < 7
              or needs_country_code(phone_raw, country)
              or not valid_phone(phone_raw, country)):
            row.action, row.reason = "rejected", "телефон не похож на настоящий"
        else:
            key = client_key(phone_raw, country)
            if key in seen:
                row.action, row.reason = "rejected", "этот номер уже есть в файле"
            else:
                seen.add(key)
                row.phone = key
        rows.append(row)
    return rows, []


def apply(store, rows: list[Row], *, tenant_id: str, country: str, commit: bool) -> dict:
    """Считает, что произойдёт, и — если `commit` — делает это.

    Существующие карточки обновляются, но не обнуляются: пустая ячейка в чужом
    файле означает «не знаю», а не «сотри заметки и имя».
    """
    created = updated = 0
    for row in rows:
        if row.action == "rejected":
            continue
        existing = store.client_by_phone(row.phone, tenant_id=tenant_id,
                                         aliases=client_keys(row.values.get("phone", ""), country))
        row.action = "updated" if existing else "created"
        if existing:
            updated += 1
        else:
            created += 1
        if not commit:
            continue

        values = row.values
        client = store.upsert_client(
            tenant_id=tenant_id, phone=row.phone,
            name=values.get("name") or (existing.name if existing else ""),
            lang=norm_lang(values.get("lang") or (existing.lang if existing else "ru")),
            consent=_flag(values.get("consent", ""), existing.consent if existing else True),
            aliases=client_keys(values.get("phone", ""), country),
        )
        patch: dict = {}
        if values.get("notes"):
            patch["notes"] = values["notes"]
        if values.get("tags"):
            patch["tags"] = [t.strip() for t in values["tags"].replace(";", ",").split(",") if t.strip()]
        if values.get("blocked"):
            patch["blocked"] = _flag(values["blocked"], False)
        if patch:
            store.patch_client(client.id, tenant_id=tenant_id, fields=patch)

    rejected = [r for r in rows if r.action == "rejected"]
    # Отклонённые — вперёд: чинить в файле нужно именно их, а список строк
    # обрезан, чтобы отчёт по базе на двадцать тысяч человек не пришлось грузить
    # в браузер целиком. Счётчики при этом считаются по всем строкам.
    shown = sorted(rows, key=lambda r: (r.action != "rejected", r.line))[:PREVIEW_LIMIT]
    return {
        "total": len(rows), "created": created, "updated": updated, "rejected": len(rejected),
        "committed": commit,
        "rows": [r.as_dict() for r in shown],
        "truncated": max(0, len(rows) - len(shown)),
    }


def export(clients) -> str:
    """Выгрузка в CSV. Разделитель — запятая, кодировка с BOM для Excel."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(EXPORT_HEADER)
    for c in clients:
        writer.writerow([
            c.name, c.phone, c.lang, c.notes, ", ".join(c.tags or []),
            "да" if c.consent else "нет", "да" if c.blocked else "нет",
            c.visits_count, c.no_show_count, c.lifetime_value, c.loyalty_balance,
            c.first_seen_at.date().isoformat() if c.first_seen_at else "",
            c.last_visit_at.date().isoformat() if c.last_visit_at else "",
        ])
    return out.getvalue()
