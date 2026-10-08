"""work locations and attendance adjustments

Revision ID: c3d5f8a1b2e4
Revises: b1c4e7a9d2f3
Create Date: 2026-10-08

Replaces the single office_settings row with saved work_locations (the existing office becomes
the default location), lets physical meetings and date overrides name a venue, and adds
admin attendance corrections (attendance_adjustments).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d5f8a1b2e4"
down_revision: Union[str, Sequence[str], None] = "b1c4e7a9d2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Work locations ---
    op.create_table(
        "work_locations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("radius_meters", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_work_locations_default", "work_locations", ["is_default"],
        unique=True, postgresql_where=sa.text("is_default"),
    )

    # The configured office (if any) becomes the default location, keeping its id.
    op.execute(
        """
        INSERT INTO work_locations (id, name, latitude, longitude, radius_meters, is_default, is_active, created_at, updated_at)
        SELECT id, location_name,
               CAST(latitude AS double precision),
               CAST(longitude AS double precision),
               CAST(ROUND(CAST(radius_meters AS numeric)) AS integer),
               true, true, now(), updated_at
        FROM office_settings
        ORDER BY updated_at DESC NULLS LAST
        LIMIT 1
        """
    )
    op.drop_table("office_settings")

    # --- Venues for physical meetings and date overrides ---
    for table in ("meetings", "work_schedule_overrides"):
        op.add_column(table, sa.Column("location_id", sa.UUID(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_location_id", table, "work_locations", ["location_id"], ["id"], ondelete="SET NULL"
        )

    # --- Attendance corrections ---
    op.create_table(
        "attendance_adjustments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("clock_in_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clock_out_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("adjusted_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["adjusted_by"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="uq_attendance_adjustment_user_date"),
    )
    op.create_index("ix_attendance_adjustments_user_id", "attendance_adjustments", ["user_id"])
    op.create_index("ix_attendance_adjustments_date", "attendance_adjustments", ["date"])


def downgrade() -> None:
    op.drop_index("ix_attendance_adjustments_date", table_name="attendance_adjustments")
    op.drop_index("ix_attendance_adjustments_user_id", table_name="attendance_adjustments")
    op.drop_table("attendance_adjustments")

    for table in ("work_schedule_overrides", "meetings"):
        op.drop_constraint(f"fk_{table}_location_id", table, type_="foreignkey")
        op.drop_column(table, "location_id")

    op.create_table(
        "office_settings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("location_name", sa.String(), nullable=False),
        sa.Column("latitude", sa.String(), nullable=False),
        sa.Column("longitude", sa.String(), nullable=False),
        sa.Column("radius_meters", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        """
        INSERT INTO office_settings (id, location_name, latitude, longitude, radius_meters, updated_at)
        SELECT id, name, CAST(latitude AS varchar), CAST(longitude AS varchar), CAST(radius_meters AS varchar), updated_at
        FROM work_locations WHERE is_default
        """
    )
    op.drop_index("uq_work_locations_default", table_name="work_locations")
    op.drop_table("work_locations")
