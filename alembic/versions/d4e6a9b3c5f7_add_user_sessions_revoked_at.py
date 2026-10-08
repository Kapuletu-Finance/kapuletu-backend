"""add users.sessions_revoked_at

Revision ID: d4e6a9b3c5f7
Revises: c3d5f8a1b2e4
Create Date: 2026-10-08

Session cut-off used by "sign out everywhere" and suspension: tokens issued before it are rejected.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e6a9b3c5f7"
down_revision: Union[str, Sequence[str], None] = "c3d5f8a1b2e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("sessions_revoked_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "sessions_revoked_at")
