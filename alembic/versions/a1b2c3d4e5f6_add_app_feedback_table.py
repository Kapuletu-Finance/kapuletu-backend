"""Add app_feedback table

Revision ID: a1b2c3d4e5f6
Revises: 620814ff5cca
Create Date: 2026-08-21 22:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '620814ff5cca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_feedback',
        sa.Column('feedback_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        # Classification
        sa.Column('feedback_type', sa.String(length=30), nullable=False),
        sa.Column('app_area', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False, server_default='medium'),
        # Content
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('what_works', sa.Text(), nullable=True),
        sa.Column('what_needs_improvement', sa.Text(), nullable=True),
        sa.Column('steps_to_reproduce', sa.Text(), nullable=True),
        sa.Column('expected_behavior', sa.Text(), nullable=True),
        # Rating
        sa.Column('overall_rating', sa.Integer(), nullable=True),
        # Admin lifecycle
        sa.Column('status', sa.String(length=20), nullable=False, server_default='new'),
        sa.Column('admin_response', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.UUID(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.user_id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id']),
        sa.PrimaryKeyConstraint('feedback_id'),
    )
    op.create_index('ix_app_feedback_user_id', 'app_feedback', ['user_id'])
    op.create_index('ix_app_feedback_status', 'app_feedback', ['status'])
    op.create_index('ix_app_feedback_feedback_type', 'app_feedback', ['feedback_type'])
    op.create_index('ix_app_feedback_created_at', 'app_feedback', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_app_feedback_created_at', table_name='app_feedback')
    op.drop_index('ix_app_feedback_feedback_type', table_name='app_feedback')
    op.drop_index('ix_app_feedback_status', table_name='app_feedback')
    op.drop_index('ix_app_feedback_user_id', table_name='app_feedback')
    op.drop_table('app_feedback')
