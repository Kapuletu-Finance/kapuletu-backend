"""fix blog_posts schema drift

Revision ID: a73ba16995e5
Revises: 38adfb369534
Create Date: 2026-10-07 17:35:45.727224

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a73ba16995e5'
down_revision: Union[str, Sequence[str], None] = '38adfb369534'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
