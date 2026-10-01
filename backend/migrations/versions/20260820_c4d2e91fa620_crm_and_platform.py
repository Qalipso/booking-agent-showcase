"""CRM, удержание, деньги и платформенные сущности.

Revision ID: c4d2e91fa620
Revises: b3f1c07ae512
Create Date: 2026-08-20 20:10:00.000000+00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "c4d2e91fa620"
down_revision = "b3f1c07ae512"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("clients",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("tenant_id", sa.String(40), nullable=False),
        sa.Column("phone", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("lang", sa.String(8), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("consent", sa.Boolean(), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_visit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("visits_count", sa.Integer(), nullable=False),
        sa.Column("no_show_count", sa.Integer(), nullable=False),
        sa.Column("lifetime_value", sa.Integer(), nullable=False),
        sa.Column("loyalty_balance", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "phone", name="uq_client_phone"),
    )
    op.create_index(op.f("ix_clients_tenant_id"), "clients", ["tenant_id"])
    op.create_index(op.f("ix_clients_phone"), "clients", ["phone"])
    op.create_index(op.f("ix_clients_blocked"), "clients", ["blocked"])

    op.create_table("locations",
        sa.Column("id", sa.String(32), nullable=False), sa.Column("tenant_id", sa.String(40), nullable=False),
        sa.Column("code", sa.String(32), nullable=False), sa.Column("name", sa.String(120), nullable=False),
        sa.Column("address", sa.Text(), nullable=False), sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_location_code"))
    op.create_index(op.f("ix_locations_tenant_id"), "locations", ["tenant_id"])
    op.create_table("resources",
        sa.Column("id", sa.String(32), nullable=False), sa.Column("tenant_id", sa.String(40), nullable=False),
        sa.Column("location_id", sa.String(32), nullable=True), sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("tenant_id", "code", name="uq_resource_code"))
    op.create_index(op.f("ix_resources_tenant_id"), "resources", ["tenant_id"])

    columns = [
        sa.Column("client_id", sa.String(32), nullable=True),
        sa.Column("lang", sa.String(8), nullable=False, server_default="ru"),
        sa.Column("source", sa.String(32), nullable=False, server_default="direct"),
        sa.Column("promo_code", sa.String(40), nullable=False, server_default=""),
        sa.Column("price_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="UYU"),
        sa.Column("paid_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payment_method", sa.String(16), nullable=False, server_default=""),
        sa.Column("discount_amount", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("location_id", sa.String(32), nullable=False, server_default="main"),
        sa.Column("group_size", sa.Integer(), nullable=False, server_default="1"),
    ]
    for column in columns:
        op.add_column("bookings", column)
    with op.batch_alter_table("bookings") as batch:
        batch.create_foreign_key("fk_bookings_client_id_clients", "clients", ["client_id"], ["id"],
                                 ondelete="SET NULL")
    op.create_index(op.f("ix_bookings_client_id"), "bookings", ["client_id"])
    op.create_index(op.f("ix_bookings_source"), "bookings", ["source"])
    op.create_index(op.f("ix_bookings_promo_code"), "bookings", ["promo_code"])
    op.create_index(op.f("ix_bookings_location_id"), "bookings", ["location_id"])
    op.add_column("notifications", sa.Column("body", sa.Text(), nullable=False, server_default=""))

    op.create_table("booking_resources",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("booking_id", sa.String(32), nullable=False), sa.Column("resource_id", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("booking_id", "resource_id", name="uq_booking_resource"))
    op.create_index(op.f("ix_booking_resources_booking_id"), "booking_resources", ["booking_id"])
    op.create_index(op.f("ix_booking_resources_resource_id"), "booking_resources", ["resource_id"])

    op.create_table("waitlist_entries",
        sa.Column("id", sa.String(32), nullable=False), sa.Column("tenant_id", sa.String(40), nullable=False),
        sa.Column("client_id", sa.String(32), nullable=False), sa.Column("service_id", sa.String(32), nullable=False),
        sa.Column("master_id", sa.String(32), nullable=False), sa.Column("date_from", sa.String(10), nullable=False),
        sa.Column("date_to", sa.String(10), nullable=False), sa.Column("time_from", sa.String(5), nullable=False),
        sa.Column("time_to", sa.String(5), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("offered_booking_id", sa.String(32), nullable=True),
        sa.Column("offer_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"), sa.PrimaryKeyConstraint("id"))
    for key in ("tenant_id", "client_id", "service_id", "status"):
        op.create_index(op.f(f"ix_waitlist_entries_{key}"), "waitlist_entries", [key])

    op.create_table("reviews",
        sa.Column("id", sa.String(32), nullable=False), sa.Column("tenant_id", sa.String(40), nullable=False),
        sa.Column("booking_id", sa.String(32), nullable=False), sa.Column("client_id", sa.String(32), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True), sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("booking_id", name="uq_review_booking"))
    for key in ("tenant_id", "booking_id", "status"):
        op.create_index(op.f(f"ix_reviews_{key}"), "reviews", [key])

    op.create_table("campaigns",
        sa.Column("id", sa.String(32), nullable=False), sa.Column("tenant_id", sa.String(40), nullable=False),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("segment", sa.String(32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("recipients_count", sa.Integer(), nullable=False), sa.Column("sent_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_campaigns_tenant_id"), "campaigns", ["tenant_id"])
    op.create_index(op.f("ix_campaigns_status"), "campaigns", ["status"])

    op.create_table("client_assets",
        sa.Column("id", sa.String(32), nullable=False), sa.Column("tenant_id", sa.String(40), nullable=False),
        sa.Column("client_id", sa.String(32), nullable=True), sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("code", sa.String(40), nullable=False), sa.Column("title", sa.String(120), nullable=False),
        sa.Column("balance_amount", sa.Integer(), nullable=False), sa.Column("remaining_uses", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("tenant_id", "code", name="uq_client_asset_code"))
    for key in ("tenant_id", "client_id", "status"):
        op.create_index(op.f(f"ix_client_assets_{key}"), "client_assets", [key])

    op.create_table("loyalty_transactions",
        sa.Column("id", sa.String(32), nullable=False), sa.Column("tenant_id", sa.String(40), nullable=False),
        sa.Column("client_id", sa.String(32), nullable=False), sa.Column("booking_id", sa.String(32), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False), sa.Column("reason", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_loyalty_transactions_tenant_id"), "loyalty_transactions", ["tenant_id"])
    op.create_index(op.f("ix_loyalty_transactions_client_id"), "loyalty_transactions", ["client_id"])

    # Существующие записи получают карточки клиентов без потери денормализованных полей.
    bind = op.get_bind()
    rows = list(bind.exec_driver_sql(
        "SELECT tenant_id, phone, client_name FROM bookings ORDER BY created_at"))
    # Карточка — одна на телефон: DISTINCT по трём полям давал по строке на
    # каждое написание имени («Эду тест», «Eduard», «Jordan Example» с одним
    # номером), и вставка падала на uq_client_phone.
    latest: dict[tuple[str, str], str] = {}
    for tenant_id, phone, name in rows:
        if name:
            latest[(tenant_id, phone)] = name
        else:
            latest.setdefault((tenant_id, phone), "")
    now = "CURRENT_TIMESTAMP"
    for (tenant_id, phone), name in latest.items():
        client_id = __import__("uuid").uuid4().hex
        bind.execute(sa.text(
            f"INSERT INTO clients (id, tenant_id, phone, name, lang, notes, tags, consent, blocked, "
            f"first_seen_at, last_seen_at, visits_count, no_show_count, lifetime_value, loyalty_balance, created_at, updated_at) "
            f"VALUES (:id,:tenant,:phone,:name,'ru','',:tags,:consent,:blocked,{now},{now},0,0,0,0,{now},{now})"
        ), {"id": client_id, "tenant": tenant_id, "phone": phone, "name": name or "", "tags": "[]",
             # Литералы 1/0 Postgres в boolean не приводит — только параметрами.
             "consent": True, "blocked": False})
        bind.execute(sa.text("UPDATE bookings SET client_id=:id WHERE tenant_id=:tenant AND phone=:phone"),
                     {"id": client_id, "tenant": tenant_id, "phone": phone})


def downgrade() -> None:
    for table in ("loyalty_transactions", "client_assets", "campaigns", "reviews", "waitlist_entries", "booking_resources"):
        op.drop_table(table)
    op.drop_column("notifications", "body")
    for index, column in (
        ("ix_bookings_location_id", "location_id"), ("ix_bookings_promo_code", "promo_code"),
        ("ix_bookings_source", "source"), ("ix_bookings_client_id", "client_id")):
        op.drop_index(index, table_name="bookings")
    with op.batch_alter_table("bookings") as batch:
        batch.drop_constraint("fk_bookings_client_id_clients", type_="foreignkey")
    for column in ("group_size", "location_id", "discount_amount", "payment_method", "paid_amount",
                   "currency", "price_amount", "promo_code", "source", "lang", "client_id"):
        op.drop_column("bookings", column)
    op.drop_table("resources")
    op.drop_table("locations")
    op.drop_table("clients")
