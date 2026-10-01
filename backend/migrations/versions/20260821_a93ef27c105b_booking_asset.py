"""booking paid by asset

Revision ID: a93ef27c105b
Revises: f1c8a52b4e77
Create Date: 2026-08-21 01:10:00.000000+00:00

Чем именно закрыт визит, если его оплатили абонементом или сертификатом.

До этой колонки способ оплаты `membership` и `certificate` в записи уже
принимался, а остаток самого абонемента при этом не менялся: отметка «оплачено
абонементом» и абонемент расходились с первой же оплаты, и остаток правили
руками. Ссылка нужна не ради отчёта, а ради идемпотентности — повторный запрос
на оплату не должен списывать посещение второй раз.

Колонка nullable без значения по умолчанию: у прежних записей абонемента не
было, и придумывать им его нечем.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'a93ef27c105b'
down_revision = 'f1c8a52b4e77'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bookings', sa.Column('asset_id', sa.String(length=32), nullable=True))
    op.create_index(op.f('ix_bookings_asset_id'), 'bookings', ['asset_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_bookings_asset_id'), table_name='bookings')
    op.drop_column('bookings', 'asset_id')
