"""master cabinet pin

Revision ID: d3a71fc9e024
Revises: b8e2f4c091ad
Create Date: 2026-08-21 08:00:00.000000+00:00

Ссылка в кабинет живёт в переписке: её пересылают, показывают на экране, она
остаётся в чате уволившегося мастера. Одной ссылки для входа стало мало —
добавлен второй фактор, четыре цифры, которые владелец передаёт отдельно.

Хранится хешем bcrypt, как пароль в панели. Счётчик неудачных попыток и время
блокировки лежат здесь же, а не в памяти процесса: четыре цифры перебираются
за вечер, и перезапуск контейнера не должен обнулять защиту.

Уже выданные ссылки остаются в базе с пустым `pin_hash` — код такие не пускает
и просит выдать новые. Это сознательно: тихо оставить дверь без второго фактора
хуже, чем попросить владельца нажать кнопку.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'd3a71fc9e024'
down_revision = 'b8e2f4c091ad'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default оставлен намеренно: без него ALTER TABLE не заполнит уже
    # выданные ключи, а снимать его пришлось бы через batch-режим, который на
    # SQLite пересобирает таблицу целиком.
    op.add_column('master_keys', sa.Column('pin_hash', sa.String(length=120),
                                           nullable=False, server_default=''))
    op.add_column('master_keys', sa.Column('pin_attempts', sa.Integer(),
                                           nullable=False, server_default='0'))
    op.add_column('master_keys', sa.Column('pin_locked_until', sa.DateTime(timezone=True),
                                           nullable=True))


def downgrade() -> None:
    op.drop_column('master_keys', 'pin_locked_until')
    op.drop_column('master_keys', 'pin_attempts')
    op.drop_column('master_keys', 'pin_hash')
