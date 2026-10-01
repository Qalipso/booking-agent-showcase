"""notification carries its template

Revision ID: c7d40a91b2e6
Revises: a93ef27c105b
Create Date: 2026-08-21 04:10:00.000000+00:00

Просьба об оценке и предложение места из листа ожидания уходят утверждённым
шаблоном WhatsApp, а не свободным текстом: вне 24-часового окна Meta свободный
текст не пропускает (`63016`), и клиент, который сам салону не писал, не
получал ни того, ни другого.

Шаблон собирается из переменных, а взять их в момент отправки неоткуда: у
просьбы об оценке запись уже `completed`, у предложения места записи нет вовсе
— есть чужая отменённая. Поэтому задача несёт переменные с собой (`variables`,
JSON) и помнит, на каком языке она собрана (`lang`): у этих двух сообщений язык
клиента, а не салона, и Content SID у каждого языка свой.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'c7d40a91b2e6'
down_revision = 'a93ef27c105b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default оставлен намеренно: без него ALTER TABLE не заполнит уже
    # стоящие в очереди строки, а снимать его пришлось бы через batch-режим,
    # который на SQLite пересобирает таблицу целиком.
    op.add_column('notifications', sa.Column('lang', sa.String(length=8), nullable=False,
                                             server_default=''))
    op.add_column('notifications', sa.Column('variables', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('notifications', 'variables')
    op.drop_column('notifications', 'lang')
