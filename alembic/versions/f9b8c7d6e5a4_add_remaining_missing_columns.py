"""Add remaining missing columns

Revision ID: f9b8c7d6e5a4
Revises: c1a7f05b19e2
Create Date: 2026-07-13 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9b8c7d6e5a4'
down_revision: Union[str, Sequence[str], None] = 'c1a7f05b19e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Plans Table
    op.add_column('plans', sa.Column('allowed_features', sa.JSON(), nullable=True))
    
    # 2. Groups Table
    op.add_column('groups', sa.Column('settings_override', sa.JSON(), nullable=True))

    # 3. Campaigns Table
    op.add_column('campaigns', sa.Column('settings_override', sa.JSON(), nullable=True))

    # 4. Transactions Table (mirroring what we did for pending_transactions)
    op.add_column('transactions', sa.Column('payment_method', sa.String(), nullable=True, server_default='Cash'))
    op.add_column('transactions', sa.Column('source_evidence', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('transactions', 'source_evidence')
    op.drop_column('transactions', 'payment_method')
    op.drop_column('campaigns', 'settings_override')
    op.drop_column('groups', 'settings_override')
    op.drop_column('plans', 'allowed_features')
