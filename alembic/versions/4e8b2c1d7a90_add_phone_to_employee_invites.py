"""add phone number to employee invitations

Revision ID: 4e8b2c1d7a90
Revises: 2ddcfebfca7f
Create Date: 2026-10-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4e8b2c1d7a90"
down_revision: Union[str, Sequence[str], None] = "2ddcfebfca7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("employee_invites", sa.Column("phone_number", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("employee_invites", "phone_number")
