"""communications: provider delivery events, open and click times

Revision ID: 7b3e9d1f4a22
Revises: 4f8a2c6d9e10
Create Date: 2026-10-08 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '7b3e9d1f4a22'
down_revision: Union[str, Sequence[str], None] = '4f8a2c6d9e10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('comm_messages', sa.Column('opened_at', sa.DateTime(), nullable=True))
    op.add_column('comm_messages', sa.Column('clicked_at', sa.DateTime(), nullable=True))
    op.create_table(
        'comm_message_events',
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('message_id', sa.UUID(), sa.ForeignKey('comm_messages.message_id', ondelete='CASCADE'),
                  nullable=True),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('provider_event_id', sa.String(length=255), nullable=False),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column('event', sa.String(length=30), nullable=False),
        sa.Column('destination', sa.String(length=255), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('payload', postgresql.JSONB(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('event_id'),
        sa.UniqueConstraint('provider', 'provider_event_id', name='uq_comm_message_events_provider_event'),
    )
    op.create_index('ix_comm_message_events_message', 'comm_message_events', ['message_id', 'occurred_at'])
    op.create_index('ix_comm_message_events_occurred', 'comm_message_events', ['occurred_at'])


def downgrade() -> None:
    op.drop_table('comm_message_events')
    op.drop_column('comm_messages', 'clicked_at')
    op.drop_column('comm_messages', 'opened_at')
