"""Add WhatsAppBlocklist

Revision ID: 620814ff5cca
Revises: add_short_code
Create Date: 2026-08-20 21:56:32.785627

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '620814ff5cca'
down_revision: Union[str, Sequence[str], None] = 'add_short_code'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'whatsapp_blocklist',
        sa.Column('phone_number', sa.String(), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('is_blocked', sa.Boolean(), nullable=False),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('phone_number')
    )
    op.create_index(op.f('ix_whatsapp_blocklist_phone_number'), 'whatsapp_blocklist', ['phone_number'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_whatsapp_blocklist_phone_number'), table_name='whatsapp_blocklist')
    op.drop_table('whatsapp_blocklist')
