"""Миграции: применяются с нуля и не расходятся с моделями.

Главный здесь — `test_models_match_migrations`. Он ловит самую дорогую ошибку
этого механизма: колонку добавили в модель, а миграцию написать забыли. Без
него расхождение всплывает уже на проде, где `create_all` больше не спасает.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from backend.app import migrate
from backend.app.db import Base

# Таблицы, которые обязаны появиться после `upgrade head`.
EXPECTED_TABLES = {
    "conversations", "messages", "bookings", "notifications",
    "tenant_secrets", "usage_counters", "clients", "locations", "resources",
    "booking_resources", "waitlist_entries", "reviews", "campaigns",
    "client_assets", "loyalty_transactions", "time_blocks",
}


@pytest.fixture
def migrated_db(tmp_path, monkeypatch):
    """Пустая база, доведённая миграциями до последней ревизии."""
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(migrate.alembic_config(), "head")
    engine = create_engine(url, future=True)
    yield engine
    engine.dispose()


def test_upgrade_creates_every_table(migrated_db):
    tables = set(inspect(migrated_db).get_table_names())
    assert EXPECTED_TABLES <= tables
    assert "alembic_version" in tables


def test_migration_head_is_recorded(migrated_db):
    assert migrate.current_revision(migrated_db) == migrate.head_revision()
    assert migrate.is_up_to_date(migrated_db)


def test_models_match_migrations(migrated_db):
    """Модели и миграции описывают одну и ту же схему.

    Расхождение означает забытую ревизию: сгенерируйте её командой
    `alembic revision --autogenerate -m "что изменилось"`.
    """
    with migrated_db.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)

    assert not diff, (
        "Модели разошлись с миграциями — не хватает ревизии.\n"
        + "\n".join(str(item) for item in diff)
    )


def test_empty_database_is_not_considered_ready(tmp_path):
    """Пустая база — не «актуальная»: приложение на ней стартовать не должно."""
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}", future=True)
    assert not migrate.is_up_to_date(engine)
    engine.dispose()


def test_downgrade_removes_schema(migrated_db, monkeypatch):
    """Откат обязан отрабатывать: миграция без обратного пути — ловушка на проде."""
    command.downgrade(migrate.alembic_config(), "base")
    remaining = set(inspect(migrated_db).get_table_names()) - {"alembic_version"}
    assert not remaining
