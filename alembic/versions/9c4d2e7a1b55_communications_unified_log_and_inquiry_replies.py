"""communications: transactional history in the outbox log, replies to website inquiries

Copies communication_logs rows that weren't part of a broadcast (receipts, invites, reminders) into
comm_messages as already-final rows, so the delivery log has one source. Nothing is re-sent.

Revision ID: 9c4d2e7a1b55
Revises: 7b3e9d1f4a22
Create Date: 2026-10-08 23:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = '9c4d2e7a1b55'
down_revision: Union[str, Sequence[str], None] = '7b3e9d1f4a22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO comm_messages (
            message_id, broadcast_id, user_id, channel, destination, category, priority, subject, context,
            status, attempts, error, sent_at, created_at, updated_at)
        SELECT l.log_id, NULL, u.user_id, lower(l.channel), lower(l.destination), 'service', 0, l.subject,
               '{"kind": "legacy"}'::jsonb,
               CASE upper(l.status) WHEN 'SENT' THEN 'sent' WHEN 'DELIVERED' THEN 'delivered' ELSE 'failed' END,
               1,
               CASE WHEN upper(l.status) IN ('SENT', 'DELIVERED') THEN NULL
                    WHEN upper(l.status) = 'QUEUED' THEN 'Never sent: interrupted before the outbox existed'
                    ELSE left(l.error_message, 2000) END,
               CASE WHEN upper(l.status) IN ('SENT', 'DELIVERED') THEN l.updated_at END,
               COALESCE(l.created_at, now()), COALESCE(l.updated_at, now())
        FROM communication_logs l
        LEFT JOIN users u ON u.user_id = l.user_id
        WHERE l.campaign_id IS NULL
        ON CONFLICT DO NOTHING
    """)
    op.create_index('ix_comm_messages_transactional', 'comm_messages', ['created_at'],
                    postgresql_where=sa.text('broadcast_id IS NULL'))

    op.create_table(
        'contact_message_replies',
        sa.Column('reply_id', sa.UUID(), nullable=False),
        sa.Column('contact_message_id', sa.UUID(),
                  sa.ForeignKey('contact_messages.id', ondelete='CASCADE'), nullable=False),
        sa.Column('author_id', sa.UUID(), sa.ForeignKey('users.user_id', ondelete='SET NULL'), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('comm_message_id', sa.UUID(), sa.ForeignKey('comm_messages.message_id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('reply_id'),
    )
    op.create_index('ix_contact_message_replies_message', 'contact_message_replies', ['contact_message_id'])


def downgrade() -> None:
    op.drop_table('contact_message_replies')
    op.drop_index('ix_comm_messages_transactional', table_name='comm_messages')
    op.execute("DELETE FROM comm_messages WHERE broadcast_id IS NULL AND context->>'kind' = 'legacy'")
