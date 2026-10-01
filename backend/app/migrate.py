"""Применение миграций схемы.

    python -m backend.app.migrate           # накатить до последней ревизии
    python -m backend.app.migrate current   # какая ревизия стоит сейчас
    python -m backend.app.migrate stamp     # отметить существующую базу как актуальную

Отдельная команда, а не вызов при старте приложения: два реплики API,
поднявшиеся одновременно, начали бы мигрировать одну базу параллельно.
В docker-compose это одноразовый сервис `migrate`, от которого зависят
остальные.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from .db import DatabaseNotConfigured, build_store

log = logging.getLogger("migrate")

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "alembic.ini"


def alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    # script_location в ini задан относительно корня репозитория — в контейнере
    # рабочий каталог тот же, но полагаться на это не стоит.
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    return config


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def is_up_to_date(engine) -> bool:
    """Схема на последней ревизии? Пустая база — не «актуальная», а неготовая."""
    try:
        return current_revision(engine) == head_revision()
    except Exception:  # noqa: BLE001 — недоступная база это не «схема устарела»
        return False


def upgrade() -> None:
    command.upgrade(alembic_config(), "head")


def stamp() -> None:
    """Отметить базу как соответствующую последней ревизии, ничего не выполняя.

    Нужно один раз для баз, созданных прежним ``create_all``: таблицы уже есть,
    и повторный `upgrade` упал бы на CREATE TABLE.
    """
    command.stamp(alembic_config(), "head")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    action = (argv or sys.argv[1:] or ["upgrade"])[0]

    try:
        store = build_store()
    except DatabaseNotConfigured as exc:
        log.error("%s", exc)
        return 2

    if action == "current":
        log.info("текущая ревизия: %s | последняя: %s",
                 current_revision(store.engine) or "нет", head_revision())
        return 0
    if action == "stamp":
        stamp()
        log.info("база отмечена как соответствующая ревизии %s", head_revision())
        return 0
    if action != "upgrade":
        log.error("неизвестная команда: %s (upgrade | current | stamp)", action)
        return 2

    before = current_revision(store.engine)
    if before is None and _has_tables(store.engine):
        # База из прежней версии: таблицы есть, истории миграций нет.
        # Накатывать начальную ревизию нельзя — она попытается создать их заново.
        stamp()
        log.warning("Найдена база без истории миграций — отмечена как %s", head_revision())
        return 0

    upgrade()
    after = current_revision(store.engine)
    if before == after:
        log.info("схема уже на последней ревизии (%s)", after)
    else:
        log.info("схема обновлена: %s → %s", before or "пусто", after)
    return 0


def _has_tables(engine) -> bool:
    from sqlalchemy import inspect

    return bool(set(inspect(engine).get_table_names()) - {"alembic_version"})


if __name__ == "__main__":
    sys.exit(main())
