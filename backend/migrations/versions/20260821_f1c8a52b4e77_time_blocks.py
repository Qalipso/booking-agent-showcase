"""time blocks

Revision ID: f1c8a52b4e77
Revises: e5b19c74d203
Create Date: 2026-08-21 00:20:00.000000+00:00

Технические перерывы мастера: обед, уборка, доставка, личное дело.

Отдельная таблица, а не запись со служебным статусом. У записи есть клиент,
услуга, деньги, уведомления и место в отчётах — перерыв внутри `bookings`
испортил бы выручку, конверсию и статистику неявок, а «клиент» по имени
«Обед» рано или поздно попал бы в рассылку.

Перерыв учитывается в занятости мастера (`Store.busy_intervals`), поэтому
свободные окна его вычитают сами — и в виджете, и у агента, и в панели.
`calendar_event_id` хранится, чтобы при удалении перерыва снять и событие из
календаря мастера: без этого в календаре остаётся висеть призрак.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'f1c8a52b4e77'
down_revision = 'e5b19c74d203'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'time_blocks',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('tenant_id', sa.String(length=40), nullable=False),
        sa.Column('master_id', sa.String(length=32), nullable=False),
        sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('calendar_event_id', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_time_blocks_tenant_id'), 'time_blocks', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_time_blocks_master_id'), 'time_blocks', ['master_id'], unique=False)
    op.create_index(op.f('ix_time_blocks_start_at'), 'time_blocks', ['start_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_time_blocks_start_at'), table_name='time_blocks')
    op.drop_index(op.f('ix_time_blocks_master_id'), table_name='time_blocks')
    op.drop_index(op.f('ix_time_blocks_tenant_id'), table_name='time_blocks')
    op.drop_table('time_blocks')
