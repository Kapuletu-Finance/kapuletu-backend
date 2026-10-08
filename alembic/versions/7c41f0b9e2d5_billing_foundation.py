"""billing foundation: settings, versioned prices, invoices, refunds, credit notes, ledger

Money columns move from Integer to Numeric(12, 2). Plans get a stable `code`.
Historical payments are turned into invoices and ledger postings by scripts/backfill_billing.py,
not here, so the result can be reviewed with --dry-run before it is written.

Revision ID: 7c41f0b9e2d5
Revises: 4e8b2c1d7a90
Create Date: 2026-10-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7c41f0b9e2d5"
down_revision: Union[str, Sequence[str], None] = "4e8b2c1d7a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MONEY = sa.Numeric(12, 2)
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # --- billing settings (single row) ---
    op.create_table(
        "billing_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="21"),
        sa.Column("grace_period_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("annual_months_charged", sa.Integer(), nullable=False, server_default="11"),
        sa.Column("addon_monthly_price", MONEY, nullable=False, server_default="200"),
        sa.Column("tax_rate_percent", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("invoice_prefix", sa.String(10), nullable=False, server_default="KPL"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", UUID, nullable=True),
        sa.CheckConstraint("id = 1", name="billing_settings_single_row"),
    )
    # Carry over the grace period already saved from the admin Billing Rules screen, if any.
    op.execute("""
        INSERT INTO billing_settings (id, grace_period_days, updated_at)
        SELECT 1,
               COALESCE((SELECT CASE WHEN config_value::text ~ '^"?[0-9]+"?$'
                                     THEN trim(both '"' from config_value::text)::int END
                         FROM system_configs WHERE config_key = 'grace_period_days'), 7),
               now()
    """)

    # --- plans: stable code, visibility, money type ---
    op.add_column("plans", sa.Column("code", sa.String(), nullable=True))
    op.execute("""
        UPDATE plans SET code = trim(both '_' from lower(regexp_replace(name, '[^A-Za-z0-9]+', '_', 'g')))
    """)
    op.alter_column("plans", "code", nullable=False)
    op.create_unique_constraint("uq_plans_code", "plans", ["code"])
    op.add_column("plans", sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("plans", sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.alter_column("plans", "price", type_=MONEY, postgresql_using="price::numeric(12,2)")

    # --- versioned prices ---
    op.create_table(
        "plan_prices",
        sa.Column("price_id", UUID, primary_key=True),
        sa.Column("plan_id", UUID, sa.ForeignKey("plans.plan_id"), nullable=False),
        sa.Column("interval", sa.String(10), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("valid_from", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("valid_to", sa.DateTime(), nullable=True),
        sa.Column("created_by", UUID, nullable=True),
        sa.CheckConstraint("interval in ('month', 'year')", name="plan_prices_interval"),
    )
    op.create_index("ix_plan_prices_plan_id", "plan_prices", ["plan_id"])
    # One open price per plan and interval.
    op.execute("CREATE UNIQUE INDEX uq_plan_prices_open ON plan_prices (plan_id, interval) WHERE valid_to IS NULL")
    # Today's prices: monthly = list price, annual = 11 months (what checkout charged until now).
    op.execute("""
        INSERT INTO plan_prices (price_id, plan_id, interval, amount, currency, valid_from)
        SELECT gen_random_uuid(), plan_id, 'month', COALESCE(price, 0), 'KES', now() FROM plans
        UNION ALL
        SELECT gen_random_uuid(), plan_id, 'year', COALESCE(price, 0) * 11, 'KES', now() FROM plans
    """)

    # --- subscriptions ---
    op.add_column("subscriptions", sa.Column("is_trial", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("subscriptions", sa.Column("price_id", UUID, sa.ForeignKey("plan_prices.price_id"), nullable=True))

    # --- invoices ---
    op.create_table(
        "invoices",
        sa.Column("invoice_id", UUID, primary_key=True),
        sa.Column("number", sa.String(), nullable=False, unique=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("subscription_id", UUID, sa.ForeignKey("subscriptions.subscription_id"), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("subtotal", MONEY, nullable=False, server_default="0"),
        sa.Column("tax", MONEY, nullable=False, server_default="0"),
        sa.Column("total", MONEY, nullable=False, server_default="0"),
        sa.Column("billing_cycle", sa.String(10), nullable=True),
        sa.Column("period_start", sa.DateTime(), nullable=True),
        sa.Column("period_end", sa.DateTime(), nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.Column("voided_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.CheckConstraint("status in ('draft', 'open', 'paid', 'void')", name="invoices_status"),
    )
    op.create_index("ix_invoices_user_id", "invoices", ["user_id"])
    op.create_index("ix_invoices_status_issued", "invoices", ["status", "issued_at"])
    op.execute("CREATE SEQUENCE IF NOT EXISTS invoice_number_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS credit_note_number_seq")

    op.create_table(
        "invoice_lines",
        sa.Column("line_id", UUID, primary_key=True),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_amount", MONEY, nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("plan_id", UUID, sa.ForeignKey("plans.plan_id"), nullable=True),
        sa.Column("price_id", UUID, sa.ForeignKey("plan_prices.price_id"), nullable=True),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])

    # --- payments ---
    op.alter_column("subscription_payments", "amount", type_=MONEY, postgresql_using="amount::numeric(12,2)")
    op.add_column("subscription_payments", sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.invoice_id"), nullable=True))
    op.create_index("ix_subscription_payments_invoice_id", "subscription_payments", ["invoice_id"])
    op.create_index("ix_subscription_payments_provider_reference", "subscription_payments", ["provider_reference"])

    # --- lifecycle history ---
    op.create_table(
        "subscription_events",
        sa.Column("event_id", UUID, primary_key=True),
        sa.Column("subscription_id", UUID, sa.ForeignKey("subscriptions.subscription_id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("from_plan_id", UUID, nullable=True),
        sa.Column("to_plan_id", UUID, nullable=True),
        sa.Column("period_end", sa.DateTime(), nullable=True),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.invoice_id"), nullable=True),
        sa.Column("actor_id", UUID, nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_subscription_events_subscription_id", "subscription_events", ["subscription_id"])
    op.create_index("ix_subscription_events_user_id", "subscription_events", ["user_id"])
    op.create_index("ix_subscription_events_created_at", "subscription_events", ["created_at"])

    # --- refunds and credit notes ---
    op.create_table(
        "refunds",
        sa.Column("refund_id", UUID, primary_key=True),
        sa.Column("payment_id", UUID, sa.ForeignKey("subscription_payments.payment_id"), nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.invoice_id"), nullable=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("reason_code", sa.String(30), nullable=False, server_default="other"),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="requested"),
        sa.Column("requested_by", UUID, nullable=True),
        sa.Column("approved_by", UUID, nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("refund_payment_id", UUID, sa.ForeignKey("subscription_payments.payment_id"), nullable=True),
        sa.CheckConstraint("status in ('requested', 'approved', 'rejected', 'paid')", name="refunds_status"),
        sa.CheckConstraint("amount > 0", name="refunds_positive"),
    )
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])
    # At most one refund in flight or done per payment (rejected ones don't count).
    op.execute("CREATE UNIQUE INDEX uq_refunds_active_payment ON refunds (payment_id) WHERE status <> 'rejected'")

    op.create_table(
        "credit_notes",
        sa.Column("credit_note_id", UUID, primary_key=True),
        sa.Column("number", sa.String(), nullable=False, unique=True),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.invoice_id"), nullable=False),
        sa.Column("user_id", UUID, sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("refund_id", UUID, sa.ForeignKey("refunds.refund_id"), nullable=True),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("issued_by", UUID, nullable=True),
        sa.Column("issued_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_credit_notes_invoice_id", "credit_notes", ["invoice_id"])

    # --- raw provider callbacks ---
    op.create_table(
        "provider_events",
        sa.Column("event_id", UUID, primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("event_key", sa.String(), nullable=False),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("outcome", sa.String(30), nullable=True),
        sa.Column("received_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("provider", "event_key", name="uix_provider_event"),
    )
    op.create_index("ix_provider_events_correlation_id", "provider_events", ["correlation_id"])

    # --- append-only double-entry ledger ---
    op.create_table(
        "billing_ledger",
        sa.Column("entry_id", UUID, primary_key=True),
        sa.Column("journal_id", UUID, nullable=False),
        sa.Column("account", sa.String(20), nullable=False),
        sa.Column("debit", MONEY, nullable=False, server_default="0"),
        sa.Column("credit", MONEY, nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="KES"),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_id", UUID, nullable=False),
        sa.Column("invoice_id", UUID, nullable=True),
        sa.Column("memo", sa.String(), nullable=True),
        sa.Column("effective_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("debit >= 0 AND credit >= 0 AND (debit = 0 OR credit = 0)", name="billing_ledger_one_side"),
        sa.CheckConstraint("account in ('cash', 'revenue', 'tax_payable', 'refunds')", name="billing_ledger_account"),
    )
    op.create_index("ix_billing_ledger_journal_id", "billing_ledger", ["journal_id"])
    op.create_index("ix_billing_ledger_user_id", "billing_ledger", ["user_id"])
    op.create_index("ix_billing_ledger_effective_at", "billing_ledger", ["effective_at"])
    # A posting for a given source happens once (e.g. a payment can't be posted twice).
    op.create_index("uq_billing_ledger_source_account", "billing_ledger", ["source_type", "source_id", "account"], unique=True)
    op.execute("""
        CREATE OR REPLACE FUNCTION billing_ledger_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'billing_ledger is append-only: post a reversing entry instead of % ', TG_OP;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER billing_ledger_no_update_delete
        BEFORE UPDATE OR DELETE ON billing_ledger
        FOR EACH ROW EXECUTE FUNCTION billing_ledger_append_only()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS billing_ledger_no_update_delete ON billing_ledger")
    op.execute("DROP FUNCTION IF EXISTS billing_ledger_append_only()")
    op.drop_table("billing_ledger")
    op.drop_table("provider_events")
    op.drop_table("credit_notes")
    op.drop_table("refunds")
    op.drop_table("subscription_events")

    op.drop_index("ix_subscription_payments_provider_reference", table_name="subscription_payments")
    op.drop_index("ix_subscription_payments_invoice_id", table_name="subscription_payments")
    op.drop_column("subscription_payments", "invoice_id")
    op.alter_column("subscription_payments", "amount", type_=sa.Integer(), postgresql_using="round(amount)::integer")

    op.drop_table("invoice_lines")
    op.drop_table("invoices")
    op.execute("DROP SEQUENCE IF EXISTS credit_note_number_seq")
    op.execute("DROP SEQUENCE IF EXISTS invoice_number_seq")

    op.drop_column("subscriptions", "price_id")
    op.drop_column("subscriptions", "is_trial")

    op.drop_table("plan_prices")

    op.alter_column("plans", "price", type_=sa.Integer(), postgresql_using="round(price)::integer")
    op.drop_column("plans", "archived_at")
    op.drop_column("plans", "is_public")
    op.drop_constraint("uq_plans_code", "plans", type_="unique")
    op.drop_column("plans", "code")

    op.drop_table("billing_settings")
