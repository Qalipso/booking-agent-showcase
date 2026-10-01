"""Окружение Alembic.

Строку подключения берём из ``DATABASE_URL``, а не из alembic.ini: пароль базы
не должен лежать в файле под git. Метаданные — те же модели, что и в рантайме,
поэтому `alembic revision --autogenerate` видит любое расхождение.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Запуск возможен и из корня репозитория, и из контейнера — путь добавляем явно.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db import Base, _normalize_url  # noqa: E402

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    url = (os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url") or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL не задан. Миграции применяются к конкретной базе — "
            "укажите строку подключения в окружении."
        )
    return _normalize_url(url)


def run_migrations_offline() -> None:
    """Генерация SQL без подключения: `alembic upgrade head --sql`."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Изменение типа колонки — тоже расхождение, молчать о нём нельзя.
            compare_type=True,
            compare_server_default=True,
            # SQLite не умеет ALTER COLUMN: batch-режим пересоздаёт таблицу.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
