"""communications: broadcasts, outbox, suppressions, template versions

Copies broadcast_campaigns and their communication_logs rows into the new tables. Copied broadcasts are
marked completed and their unsent messages failed, so the dispatcher never re-sends history.
The old tables stay for one release; drop them once the new hub is confirmed in production.

Revision ID: 4f8a2c6d9e10
Revises: e70212aba69d
Create Date: 2026-10-08 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '4f8a2c6d9e10'
down_revision: Union[str, Sequence[str], None] = 'e70212aba69d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'comm_broadcasts',
        sa.Column('broadcast_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('audience', postgresql.JSONB(), nullable=False),
        sa.Column('channels', postgresql.JSONB(), nullable=False),
        sa.Column('content', postgresql.JSONB(), nullable=False),
        sa.Column('created_by', sa.UUID(), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('approved_by', sa.UUID(), sa.ForeignKey('users.user_id'), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('decision_note', sa.Text(), nullable=True),
        sa.Column('scheduled_for', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('recipients_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stats', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('legacy_campaign_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('broadcast_id'),
    )
    op.create_index('ix_comm_broadcasts_status_due', 'comm_broadcasts', ['status', 'scheduled_for'])
    op.create_index('ix_comm_broadcasts_created_at', 'comm_broadcasts', ['created_at'])

    op.create_table(
        'comm_messages',
        sa.Column('message_id', sa.UUID(), nullable=False),
        sa.Column('broadcast_id', sa.UUID(), sa.ForeignKey('comm_broadcasts.broadcast_id', ondelete='CASCADE'),
                  nullable=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.user_id', ondelete='SET NULL'), nullable=True),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('destination', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('priority', sa.SmallInteger(), nullable=False, server_default='5'),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('context', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('next_attempt_at', sa.DateTime(), nullable=True),
        sa.Column('claimed_at', sa.DateTime(), nullable=True),
        sa.Column('provider', sa.String(length=30), nullable=True),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('message_id'),
        sa.UniqueConstraint('broadcast_id', 'user_id', 'channel', name='uq_comm_messages_broadcast_user_channel'),
    )
    op.create_index('ix_comm_messages_due', 'comm_messages', ['status', 'priority', 'next_attempt_at'])
    op.create_index('ix_comm_messages_broadcast', 'comm_messages', ['broadcast_id', 'status'])
    op.create_index('ix_comm_messages_user', 'comm_messages', ['user_id'])
    op.create_index('ix_comm_messages_provider_id', 'comm_messages', ['provider_message_id'])
    op.create_index('ix_comm_messages_created_at', 'comm_messages', ['created_at'])

    op.create_table(
        'comm_suppressions',
        sa.Column('suppression_id', sa.UUID(), nullable=False),
        sa.Column('channel', sa.String(length=20), nullable=False),
        sa.Column('destination', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('reason', sa.String(length=30), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.user_id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_by', sa.UUID(), sa.ForeignKey('users.user_id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('suppression_id'),
        sa.UniqueConstraint('channel', 'destination', 'category', name='uq_comm_suppressions_destination'),
    )

    op.create_table(
        'comm_template_versions',
        sa.Column('version_id', sa.UUID(), nullable=False),
        sa.Column('template_name', sa.String(length=100), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.Column('created_by', sa.UUID(), sa.ForeignKey('users.user_id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('version_id'),
        sa.UniqueConstraint('template_name', 'version', name='uq_comm_template_versions'),
    )

    # --- history ---
    op.execute("""
        INSERT INTO comm_broadcasts (
            broadcast_id, title, category, status, audience, channels, content, recipients_count, stats,
            legacy_campaign_id, started_at, completed_at, created_at, updated_at)
        SELECT campaign_id, title,
               CASE WHEN target_audience = 'marketing_opt_in' THEN 'marketing' ELSE 'service' END,
               'completed',
               jsonb_build_object('type', 'legacy', 'label', target_audience),
               channels::jsonb,
               jsonb_build_object('email', jsonb_build_object('subject', title, 'html', message_body)),
               COALESCE(recipients_count, 0), '{}'::jsonb,
               campaign_id, created_at, created_at, COALESCE(created_at, now()), COALESCE(created_at, now())
        FROM broadcast_campaigns
    """)
    op.execute("""
        INSERT INTO comm_messages (
            message_id, broadcast_id, user_id, channel, destination, category, priority, subject, context,
            status, attempts, error, sent_at, created_at, updated_at)
        SELECT l.log_id, l.campaign_id, u.user_id, lower(l.channel), l.destination, b.category, 5, l.subject,
               '{}'::jsonb,
               CASE upper(l.status) WHEN 'SENT' THEN 'sent' WHEN 'DELIVERED' THEN 'delivered' ELSE 'failed' END,
               1,
               CASE WHEN upper(l.status) IN ('SENT', 'DELIVERED') THEN NULL
                    WHEN upper(l.status) = 'QUEUED' THEN 'Never sent: interrupted before the outbox existed'
                    ELSE left(l.error_message, 2000) END,
               CASE WHEN upper(l.status) IN ('SENT', 'DELIVERED') THEN l.updated_at END,
               COALESCE(l.created_at, now()), COALESCE(l.updated_at, now())
        FROM communication_logs l
        JOIN comm_broadcasts b ON b.broadcast_id = l.campaign_id
        LEFT JOIN users u ON u.user_id = l.user_id
        WHERE l.campaign_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)
    op.create_index('ix_communication_logs_created_at', 'communication_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_communication_logs_created_at', table_name='communication_logs')
    op.drop_table('comm_template_versions')
    op.drop_table('comm_suppressions')
    op.drop_table('comm_messages')
    op.drop_table('comm_broadcasts')
