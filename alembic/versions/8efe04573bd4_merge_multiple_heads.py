"""merge multiple heads

Revision ID: 8efe04573bd4
Revises: 21645580aa6c, ff1234567890
Create Date: 2026-08-28 11:59:52.190451

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8efe04573bd4'
down_revision: Union[str, Sequence[str], None] = ('21645580aa6c', 'ff1234567890')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
