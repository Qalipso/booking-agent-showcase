"""master cabinet access

Revision ID: b8e2f4c091ad
Revises: c7d40a91b2e6
Create Date: 2026-08-21 12:00:00.000000+00:00

У мастера появился свой кабинет: он видит, кто к нему записан, и правит свой
график. Пускать его в панель нельзя — там выручка салона, клиентская база и
ключи интеграций, — а заводить ему пользователя с паролем и вторым фактором
значит гарантированно получить звонок владельцу в первый же занятый день.

Поэтому вход по личной ссылке. В базе — только SHA-256 ключа: дамп базы
кабинета не открывает. Ссылка одна на мастера (уникальность по паре
бизнес+мастер), новая выдача гасит старую, а вместе с ней — каскадом — и все
открытые по ней сессии.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'b8e2f4c091ad'
down_revision = 'c7d40a91b2e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'master_keys',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(length=40), nullable=False),
        sa.Column('master_id', sa.String(length=32), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('tenant_id', 'master_id', name='uq_master_key'),
    )
    op.create_index('ix_master_keys_tenant_id', 'master_keys', ['tenant_id'])
    op.create_index('ix_master_keys_master_id', 'master_keys', ['master_id'])
    op.create_index('ix_master_keys_key_hash', 'master_keys', ['key_hash'], unique=True)

    op.create_table(
        'master_sessions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        # Отзыв ссылки обязан закрывать открытые кабинеты, иначе «отозвал»
        # означает «отозвал на следующие два месяца».
        sa.Column('key_id', sa.Integer(),
                  sa.ForeignKey('master_keys.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_master_sessions_token_hash', 'master_sessions', ['token_hash'], unique=True)
    op.create_index('ix_master_sessions_key_id', 'master_sessions', ['key_id'])
    op.create_index('ix_master_sessions_expires_at', 'master_sessions', ['expires_at'])


def downgrade() -> None:
    op.drop_table('master_sessions')
    op.drop_table('master_keys')
