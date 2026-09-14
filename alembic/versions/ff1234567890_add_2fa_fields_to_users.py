"""add 2fa fields to users

Revision ID: ff1234567890
Revises: 
Create Date: 2026-08-28 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff1234567890'
down_revision: Union[str, None] = 'ee7f2a5d3f2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('two_factor_enabled', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('two_factor_channel', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'two_factor_channel')
    op.drop_column('users', 'two_factor_enabled')
