"""add slugs for admin lookups

Revision ID: a1b2c3d4e5f7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-21 23:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add slug column to users
    op.add_column('users', sa.Column('slug', sa.String(), nullable=True))
    op.create_index(op.f('ix_users_slug'), 'users', ['slug'], unique=True)

    # Add reference_number column to app_feedback
    op.add_column('app_feedback', sa.Column('reference_number', sa.String(), nullable=True))
    op.create_index(op.f('ix_app_feedback_reference_number'), 'app_feedback', ['reference_number'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_app_feedback_reference_number'), table_name='app_feedback')
    op.drop_column('app_feedback', 'reference_number')
    
    op.drop_index(op.f('ix_users_slug'), table_name='users')
    op.drop_column('users', 'slug')
