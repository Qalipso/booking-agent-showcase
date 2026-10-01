"""Начальная схема: диалоги, записи, уведомления, секреты, счётчики тарифа.

Соответствует состоянию моделей на момент перехода на единый FastAPI-контур.
База, созданная раньше через create_all, отмечается как применённая:
`alembic stamp head` — таблицы уже существуют, повторно их создавать нельзя.

Revision ID: 23345dd71df0
Revises: 
Create Date: 2026-08-05 18:28:32.626289+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '23345dd71df0'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('bookings',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('tenant_id', sa.String(length=40), nullable=False),
    sa.Column('conversation_id', sa.String(length=32), nullable=True),
    sa.Column('master_id', sa.String(length=32), nullable=False),
    sa.Column('service_id', sa.String(length=32), nullable=False),
    sa.Column('start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('end_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('client_name', sa.String(length=120), nullable=False),
    sa.Column('phone', sa.String(length=40), nullable=False),
    sa.Column('comment', sa.Text(), nullable=False),
    sa.Column('event_id', sa.String(length=256), nullable=True),
    sa.Column('html_link', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('requires_confirmation', sa.Boolean(), nullable=False),
    sa.Column('confirmed_by_client', sa.Boolean(), nullable=False),
    sa.Column('idempotency_key', sa.String(length=64), nullable=True),
    sa.Column('notify_consent', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('idempotency_key', name='uq_idempotency'),
    sa.UniqueConstraint('tenant_id', 'master_id', 'start_at', name='uq_master_slot')
    )
    op.create_index(op.f('ix_bookings_conversation_id'), 'bookings', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_bookings_master_id'), 'bookings', ['master_id'], unique=False)
    op.create_index(op.f('ix_bookings_phone'), 'bookings', ['phone'], unique=False)
    op.create_index(op.f('ix_bookings_start_at'), 'bookings', ['start_at'], unique=False)
    op.create_index(op.f('ix_bookings_status'), 'bookings', ['status'], unique=False)
    op.create_index(op.f('ix_bookings_tenant_id'), 'bookings', ['tenant_id'], unique=False)
    op.create_table('conversations',
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('tenant_id', sa.String(length=40), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('external_id', sa.String(length=64), nullable=True),
    sa.Column('state', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversations_external_id'), 'conversations', ['external_id'], unique=False)
    op.create_index(op.f('ix_conversations_tenant_id'), 'conversations', ['tenant_id'], unique=False)
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('notification_id', sa.String(length=160), nullable=False),
    sa.Column('tenant_id', sa.String(length=40), nullable=False),
    sa.Column('booking_id', sa.String(length=32), nullable=False),
    sa.Column('type', sa.String(length=40), nullable=False),
    sa.Column('audience', sa.String(length=16), nullable=False),
    sa.Column('provider', sa.String(length=16), nullable=False),
    sa.Column('channel', sa.String(length=16), nullable=False),
    sa.Column('recipient', sa.String(length=160), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('booking_start_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('provider_message_id', sa.String(length=120), nullable=True),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('fallback_of', sa.String(length=160), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('notification_id', name='uq_notification_name')
    )
    op.create_index(op.f('ix_notifications_booking_id'), 'notifications', ['booking_id'], unique=False)
    op.create_index(op.f('ix_notifications_notification_id'), 'notifications', ['notification_id'], unique=False)
    op.create_index(op.f('ix_notifications_provider_message_id'), 'notifications', ['provider_message_id'], unique=False)
    op.create_index(op.f('ix_notifications_scheduled_at'), 'notifications', ['scheduled_at'], unique=False)
    op.create_index(op.f('ix_notifications_status'), 'notifications', ['status'], unique=False)
    op.create_index(op.f('ix_notifications_tenant_id'), 'notifications', ['tenant_id'], unique=False)
    op.create_table('tenant_secrets',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=40), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'key', name='uq_tenant_secret')
    )
    op.create_index(op.f('ix_tenant_secrets_tenant_id'), 'tenant_secrets', ['tenant_id'], unique=False)
    op.create_table('usage_counters',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=40), nullable=False),
    sa.Column('period', sa.String(length=7), nullable=False),
    sa.Column('metric', sa.String(length=24), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tenant_id', 'period', 'metric', name='uq_usage')
    )
    op.create_index(op.f('ix_usage_counters_period'), 'usage_counters', ['period'], unique=False)
    op.create_index(op.f('ix_usage_counters_tenant_id'), 'usage_counters', ['tenant_id'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('conversation_id', sa.String(length=32), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_usage_counters_tenant_id'), table_name='usage_counters')
    op.drop_index(op.f('ix_usage_counters_period'), table_name='usage_counters')
    op.drop_table('usage_counters')
    op.drop_index(op.f('ix_tenant_secrets_tenant_id'), table_name='tenant_secrets')
    op.drop_table('tenant_secrets')
    op.drop_index(op.f('ix_notifications_tenant_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_status'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_scheduled_at'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_provider_message_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_notification_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_booking_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_conversations_tenant_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_external_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_index(op.f('ix_bookings_tenant_id'), table_name='bookings')
    op.drop_index(op.f('ix_bookings_status'), table_name='bookings')
    op.drop_index(op.f('ix_bookings_start_at'), table_name='bookings')
    op.drop_index(op.f('ix_bookings_phone'), table_name='bookings')
    op.drop_index(op.f('ix_bookings_master_id'), table_name='bookings')
    op.drop_index(op.f('ix_bookings_conversation_id'), table_name='bookings')
    op.drop_table('bookings')
