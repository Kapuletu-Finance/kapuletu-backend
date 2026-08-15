"""Add inbox history fields

Revision ID: hist_history123
Revises: ee7f2a5d3f2a
Create Date: 2026-08-15 04:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'hist_history123'
down_revision: Union[str, Sequence[str], None] = 'ee7f2a5d3f2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pending_transactions', sa.Column('processed_at', sa.DateTime(), nullable=True))
    op.add_column('pending_transactions', sa.Column('processed_by', sa.UUID(as_uuid=True), nullable=True))
    op.add_column('pending_transactions', sa.Column('rejection_reason', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('pending_transactions', 'rejection_reason')
    op.drop_column('pending_transactions', 'processed_by')
    op.drop_column('pending_transactions', 'processed_at')
