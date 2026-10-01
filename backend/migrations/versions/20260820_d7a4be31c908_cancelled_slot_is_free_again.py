"""cancelled slot is free again

Revision ID: d7a4be31c908
Revises: c4d2e91fa620
Create Date: 2026-08-20 22:40:00.000000+00:00

Отменённая запись больше не держит слот навсегда.

`uq_master_slot` был безусловным: (бизнес, мастер, начало). Отменённая строка
остаётся в таблице ради статистики — и занимала этот ключ вечно. Сетка окон
показывала время свободным (занятость считается только по confirmed и
completed), клиент выбирал его, заполнял имя и телефон, а «Подтвердить»
отвечало «это время только что заняли». Навсегда, для любого клиента.

По той же причине не работал лист ожидания: освободившееся место предлагалось,
но вставка новой записи на него падала на этом же индексе.

Индекс становится частичным — он действует только для активных записей.
Защита от гонки не слабеет: два одновременных подтверждения по-прежнему
упираются в него, а на Postgres поверх лежит EXCLUDE-ограничение против
пересечений (ревизия b3f1c07ae512).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'd7a4be31c908'
down_revision = 'c4d2e91fa620'
branch_labels = None
depends_on = None

ACTIVE = "status IN ('confirmed', 'completed')"


def upgrade() -> None:
    # SQLite не умеет удалять ограничение на месте — batch пересобирает таблицу.
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_constraint('uq_master_slot', type_='unique')
    op.create_index('uq_master_slot', 'bookings', ['tenant_id', 'master_id', 'start_at'],
                    unique=True, sqlite_where=sa.text(ACTIVE), postgresql_where=sa.text(ACTIVE))


def downgrade() -> None:
    op.drop_index('uq_master_slot', table_name='bookings')
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_master_slot', ['tenant_id', 'master_id', 'start_at'])
