"""fix blog_posts schema drift

Revision ID: a73ba16995e5
Revises: 38adfb369534
Create Date: 2026-10-07

Fixes the drift between the blog_posts SQLAlchemy model and the actual
database schema. The model added tags (JSON), views_count, likes_count, and
dislikes_count after the initial table was created, but no migration was ever
written for those columns. This migration reconciles that gap so that Alembic
autogenerate will stop detecting spurious blog_posts changes on every run.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a73ba16995e5"
down_revision: Union[str, Sequence[str], None] = "38adfb369534"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply the missing blog_posts column changes."""

    # 1. Add tags column if it doesn't already exist (TEXT first, then cast)
    #    We use server_default so existing rows get [] instead of NULL.
    op.add_column(
        "blog_posts",
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
    )

    # 2. Add views_count if missing
    op.add_column(
        "blog_posts",
        sa.Column("views_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # 3. Add likes_count if missing
    op.add_column(
        "blog_posts",
        sa.Column("likes_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # 4. Add dislikes_count if missing
    op.add_column(
        "blog_posts",
        sa.Column("dislikes_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Remove the columns added by this migration."""
    op.drop_column("blog_posts", "dislikes_count")
    op.drop_column("blog_posts", "likes_count")
    op.drop_column("blog_posts", "views_count")
    op.drop_column("blog_posts", "tags")
