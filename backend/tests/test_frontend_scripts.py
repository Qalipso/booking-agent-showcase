"""Проверки браузерного кода, который иначе никто не проверяет.

Фронтенд собирается без сборщика и без линтера: файлы подключаются тегом
`<script>` как есть. Значит две функции с одним именем в одном файле — не ошибка
сборки, а тихая подмена: объявления всплывают, последнее затирает первое, и
вызывающая сторона получает чужую функцию. Именно так экран «Записи» в панели
падал на `items.filter is not a function` — `rowActions` для строки записи была
перекрыта одноимённой функцией раздела «Платформа».
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

PUBLIC = Path(__file__).resolve().parents[2] / "public"
SCRIPTS = sorted(PUBLIC.rglob("*.js"))
# Вендорные библиотеки не наши: их сборка сама следит за именами.
OURS = [p for p in SCRIPTS if "vendor" not in p.parts]

DECLARATION = re.compile(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", re.M)


@pytest.mark.parametrize("script", OURS, ids=lambda p: p.name)
def test_no_duplicate_function_declarations(script: Path) -> None:
    names = Counter(DECLARATION.findall(script.read_text(encoding="utf-8")))
    duplicates = {name: count for name, count in names.items() if count > 1}
    assert not duplicates, (
        f"{script.relative_to(PUBLIC.parent)}: имя объявлено дважды — "
        f"позднее объявление молча заменит раннее: {duplicates}"
    )


def test_scripts_found() -> None:
    """Страховка от переезда каталога: пустой список проверок всегда «зелёный»."""
    assert len(OURS) >= 5
