"""Add missing models for audit and ingestion

Revision ID: c1a7f05b19e2
Revises: b529d1c1a8e4
Create Date: 2026-07-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a7f05b19e2'
down_revision: Union[str, Sequence[str], None] = 'b529d1c1a8e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Audit Logs Table
    op.create_table(
        'audit_logs',
        sa.Column('log_id', sa.UUID(), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_id', sa.String(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('log_id')
    )

    # 2. AI Feedback Table
    op.create_table(
        'ai_feedback',
        sa.Column('feedback_id', sa.UUID(), nullable=False),
        sa.Column('pending_transaction_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('original_parsed_data', sa.JSON(), nullable=False),
        sa.Column('corrected_data', sa.JSON(), nullable=False),
        sa.Column('is_reviewed', sa.Boolean(), nullable=True),
        sa.Column('is_approved_for_training', sa.Boolean(), nullable=True),
        sa.Column('reviewed_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['pending_transaction_id'], ['pending_transactions.pending_id'], ),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.user_id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('feedback_id')
    )

    # 3. Campaign Report Settings Table
    op.create_table(
        'campaign_report_settings',
        sa.Column('campaign_id', sa.UUID(), nullable=False),
        sa.Column('header_template', sa.String(), nullable=True),
        sa.Column('footer_template', sa.String(), nullable=True),
        sa.Column('use_emojis', sa.Boolean(), nullable=True),
        sa.Column('show_status_text', sa.Boolean(), nullable=True),
        sa.Column('blank_slots_count', sa.Integer(), nullable=True),
        sa.Column('public_access_pin', sa.String(length=4), nullable=True),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.campaign_id'], ),
        sa.PrimaryKeyConstraint('campaign_id')
    )

    # 4. Support Tickets Table
    op.create_table(
        'support_tickets',
        sa.Column('ticket_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('priority', sa.String(length=10), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('assigned_admin_id', sa.UUID(), nullable=True),
        sa.Column('internal_notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['assigned_admin_id'], ['users.user_id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.PrimaryKeyConstraint('ticket_id')
    )

    # 5. Missing Columns in pending_transactions
    op.add_column('pending_transactions', sa.Column('payment_method', sa.String(), nullable=True, server_default='Cash'))
    op.add_column('pending_transactions', sa.Column('source_evidence', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('pending_transactions', 'source_evidence')
    op.drop_column('pending_transactions', 'payment_method')
    
    op.drop_table('support_tickets')
    op.drop_table('campaign_report_settings')
    op.drop_table('ai_feedback')
    op.drop_table('audit_logs')
