"""finance reconciliation runs and items, scheduled finance reports

Revision ID: 9e2b7d4c1a63
Revises: 7c41f0b9e2d5
Create Date: 2026-10-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9e2b7d4c1a63"
down_revision: Union[str, Sequence[str], None] = "7c41f0b9e2d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)
MONEY = sa.Numeric(12, 2)


def upgrade() -> None:
    op.create_table(
        "reconciliation_runs",
        sa.Column("run_id", UUID, primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_name", sa.String(), nullable=True),
        sa.Column("period_start", sa.DateTime(), nullable=True),
        sa.Column("period_end", sa.DateTime(), nullable=True),
        sa.Column("lines", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mismatched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "reconciliation_items",
        sa.Column("item_id", UUID, primary_key=True),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("ref_key", sa.String(), nullable=False),
        sa.Column("provider_ref", sa.String(), nullable=True),
        sa.Column("provider_amount", MONEY, nullable=True),
        sa.Column("provider_at", sa.DateTime(), nullable=True),
        sa.Column("counterparty", sa.String(), nullable=True),
        sa.Column("payment_id", UUID, nullable=True),
        sa.Column("ledger_amount", MONEY, nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("match_method", sa.String(20), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("resolution_note", sa.String(), nullable=True),
        sa.Column("resolved_by", UUID, nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "ref_key", name="uix_reconciliation_item_ref"),
        sa.CheckConstraint(
            "status in ('matched', 'amount_mismatch', 'missing_in_ledger', 'missing_in_statement')",
            name="reconciliation_items_status",
        ),
    )
    op.create_index("ix_reconciliation_items_run_id", "reconciliation_items", ["run_id"])
    op.create_index("ix_reconciliation_items_payment_id", "reconciliation_items", ["payment_id"])
    op.create_index("ix_reconciliation_items_status", "reconciliation_items", ["status"])

    op.create_table(
        "report_schedules",
        sa.Column("schedule_id", UUID, primary_key=True),
        sa.Column("report_type", sa.String(30), nullable=False),
        sa.Column("frequency", sa.String(10), nullable=False),
        sa.Column("format", sa.String(10), nullable=False, server_default="pdf"),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_period_end", sa.DateTime(), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_by", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("frequency in ('weekly', 'monthly')", name="report_schedules_frequency"),
        sa.CheckConstraint("format in ('csv', 'excel', 'pdf')", name="report_schedules_format"),
    )


def downgrade() -> None:
    op.drop_table("report_schedules")
    op.drop_table("reconciliation_items")
    op.drop_table("reconciliation_runs")
