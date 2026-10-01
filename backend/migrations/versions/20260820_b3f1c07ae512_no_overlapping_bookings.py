"""no overlapping bookings

Revision ID: b3f1c07ae512
Revises: a8a75b0fed73
Create Date: 2026-08-20 18:20:00.000000+00:00

Запрет пересекающихся записей одного мастера на уровне базы.

Уникальный индекс (tenant_id, master_id, start_at) ловил только совпадение
начала. Услуга на три часа занимает три часа: запись в её середину начинается
в другую минуту, индекс её пропускал, и защищала только проверка в коде — а
она не переживает двух одновременных запросов.

EXCLUDE — расширение Postgres поверх GiST, на SQLite его нет. Там остаётся
проверка в транзакции вставки (`Store.create_booking`), чего для локального
запуска и тестов достаточно: параллельных писателей в них нет.

Если в базе уже есть пересечения, ограничение не создаётся: миграция пишет их
в лог и идёт дальше. Уронить деплой работающего салона хуже, чем оставить
защиту на коде ещё на один релиз, — но молчать об этом нельзя, поэтому
конфликтующие записи перечислены поимённо.
"""

from __future__ import annotations

import logging

from alembic import op

revision = 'b3f1c07ae512'
down_revision = 'a8a75b0fed73'
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

CONSTRAINT = "excl_booking_overlap"

CONFLICTS = """
SELECT a.id, b.id, a.master_id, a.start_at
FROM bookings a JOIN bookings b
  ON a.tenant_id = b.tenant_id AND a.master_id = b.master_id AND a.id < b.id
 AND a.start_at < b.end_at AND b.start_at < a.end_at
WHERE a.status IN ('confirmed', 'completed') AND b.status IN ('confirmed', 'completed')
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    rows = list(bind.exec_driver_sql(CONFLICTS))
    if rows:
        for first, second, master, start in rows:
            log.warning("Пересечение записей %s и %s (мастер %s, %s) — "
                        "ограничение %s не создано", first, second, master, start, CONSTRAINT)
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(
        f"ALTER TABLE bookings ADD CONSTRAINT {CONSTRAINT} "
        "EXCLUDE USING gist ("
        "  tenant_id WITH =, master_id WITH =,"
        "  tstzrange(start_at, end_at, '[)') WITH &&"
        ") WHERE (status IN ('confirmed', 'completed'))"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f"ALTER TABLE bookings DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
