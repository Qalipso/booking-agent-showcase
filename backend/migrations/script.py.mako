"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

ПРОВЕРЬТЕ ПЕРЕД КОММИТОМ:
  * Новая NOT NULL колонка требует server_default — иначе миграция упадёт на
    таблице с данными: «column ... contains null values». Autogenerate про
    существующие строки не знает.
  * downgrade() должен возвращать схему назад: миграция без обратного пути
    превращает неудачный деплой в ручную починку прода.
  * Данные не переносятся сами. Переименование колонки autogenerate видит как
    «удалить одну, добавить другую» — то есть как потерю данных.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
