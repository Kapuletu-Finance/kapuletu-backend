"""Add short_code to campaign

Revision ID: add_short_code
Revises: 
Create Date: 2026-08-15 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_short_code'
down_revision: Union[str, Sequence[str], None] = 'hist_history123'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('campaigns', sa.Column('short_code', sa.String(length=8), nullable=True))
    op.create_index(op.f('ix_campaigns_short_code'), 'campaigns', ['short_code'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_campaigns_short_code'), table_name='campaigns')
    op.drop_column('campaigns', 'short_code')
