"""shared group sessions

Revision ID: e5b19c74d203
Revises: d7a4be31c908
Create Date: 2026-08-20 23:40:00.000000+00:00

Курс на десять мест продаётся десяти клиентам, а не одному.

Услуга с `groupCapacity` больше единицы — это общая сессия: она занимает время
мастера целиком, но вмещает несколько клиентов. В модели такие записи ничем не
отличались от обычных, поэтому вторую отбивал уникальный индекс по началу, а до
него — проверка пересечения. Мест десять, продать можно было одно.

Колонка `shared` помечает место в общей сессии. Оба защитных ограничения —
уникальный индекс по началу и EXCLUDE против пересечений — теперь действуют
только для обычных записей: для них ничего не меняется. Вместимость сессии
считает код в той же транзакции, что и вставку (`Store.create_booking`), а
пересечение общей сессии с обычной записью он же и запрещает.
"""

from __future__ import annotations

import logging

from alembic import op
import sqlalchemy as sa

log = logging.getLogger("alembic.runtime.migration")

revision = 'e5b19c74d203'
down_revision = 'd7a4be31c908'
branch_labels = None
depends_on = None

ACTIVE = "status IN ('confirmed', 'completed')"
EXCLUSIVE_SQLITE = f"{ACTIVE} AND shared = 0"
EXCLUSIVE_PG = f"{ACTIVE} AND NOT shared"

# Пересечения среди тех записей, на которые ограничение и распространяется:
# места одной групповой сессии друг другу не мешают и в счёт не идут.
CONFLICTS = f"""
SELECT a.id, b.id, a.master_id, a.start_at
FROM bookings a JOIN bookings b
  ON a.tenant_id = b.tenant_id AND a.master_id = b.master_id AND a.id < b.id
 AND a.start_at < b.end_at AND b.start_at < a.end_at
WHERE ({EXCLUSIVE_PG.replace('status', 'a.status').replace('shared', 'a.shared')})
  AND ({EXCLUSIVE_PG.replace('status', 'b.status').replace('shared', 'b.shared')})
"""


def upgrade() -> None:
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('shared', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.create_index(batch_op.f('ix_bookings_shared'), ['shared'], unique=False)

    op.drop_index('uq_master_slot', table_name='bookings')
    op.create_index('uq_master_slot', 'bookings', ['tenant_id', 'master_id', 'start_at'],
                    unique=True, sqlite_where=sa.text(EXCLUSIVE_SQLITE),
                    postgresql_where=sa.text(EXCLUSIVE_PG))

    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS excl_booking_overlap")
    # Та же осторожность, что и в ревизии b3f1c07ae512: если в базе уже есть
    # пересекающиеся записи, ограничение не создастся, и деплой работающего
    # салона упал бы вместе со всем контейнером. Конфликты называем поимённо и
    # идём дальше — защита остаётся на проверке в коде.
    rows = list(bind.exec_driver_sql(CONFLICTS))
    if rows:
        for first, second, master, start in rows:
            log.warning("Пересечение записей %s и %s (мастер %s, %s) — "
                        "ограничение excl_booking_overlap не создано", first, second, master, start)
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        "ALTER TABLE bookings ADD CONSTRAINT excl_booking_overlap "
        "EXCLUDE USING gist ("
        "  tenant_id WITH =, master_id WITH =,"
        "  tstzrange(start_at, end_at, '[)') WITH &&"
        f") WHERE ({EXCLUSIVE_PG})"
    )


def downgrade() -> None:
    op.drop_index('uq_master_slot', table_name='bookings')
    op.create_index('uq_master_slot', 'bookings', ['tenant_id', 'master_id', 'start_at'],
                    unique=True, sqlite_where=sa.text(ACTIVE), postgresql_where=sa.text(ACTIVE))
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS excl_booking_overlap")
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bookings_shared'))
        batch_op.drop_column('shared')
