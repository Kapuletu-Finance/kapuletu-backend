"""hr work schedule and meeting attendance

Revision ID: b1c4e7a9d2f3
Revises: a73ba16995e5
Create Date: 2026-10-08

Adds the weekly work schedule (company-wide and per-employee) with date overrides,
lateness tracking on daily reports, and the meeting lifecycle / RSVP / check-in /
reminder fields. Also unifies the attendance vocabulary ('remote' -> 'online').
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c4e7a9d2f3"
down_revision: Union[str, Sequence[str], None] = "a73ba16995e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Work schedule ---
    op.create_table(
        "work_schedule_days",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("cutoff_time", sa.Time(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "weekday", name="uq_work_schedule_user_weekday"),
    )
    op.create_index("ix_work_schedule_days_user_id", "work_schedule_days", ["user_id"])
    op.create_index(
        "uq_work_schedule_company_weekday", "work_schedule_days", ["weekday"],
        unique=True, postgresql_where=sa.text("user_id IS NULL"),
    )

    op.create_table(
        "work_schedule_overrides",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.user_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "date", name="uq_work_schedule_override_user_date"),
    )
    op.create_index("ix_work_schedule_overrides_user_id", "work_schedule_overrides", ["user_id"])
    op.create_index("ix_work_schedule_overrides_date", "work_schedule_overrides", ["date"])
    op.create_index(
        "uq_work_schedule_override_company_date", "work_schedule_overrides", ["date"],
        unique=True, postgresql_where=sa.text("user_id IS NULL"),
    )

    # --- Daily reports ---
    op.add_column(
        "employee_reports",
        sa.Column("is_late", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.execute("UPDATE employee_reports SET work_mode = 'online' WHERE work_mode = 'remote'")

    # --- Meetings ---
    op.add_column("meetings", sa.Column("status", sa.String(), nullable=False, server_default="scheduled"))
    op.add_column("meetings", sa.Column("audience", sa.String(), nullable=False, server_default="custom"))
    op.add_column("meetings", sa.Column("audience_roles", sa.JSON(), nullable=True))
    op.add_column("meetings", sa.Column("attendance_finalized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("meetings", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    # --- Meeting attendees ---
    # Remove duplicate invitations (keep one row per meeting/user) before enforcing uniqueness.
    op.execute(
        """
        DELETE FROM meeting_attendees a
        USING meeting_attendees b
        WHERE a.meeting_id = b.meeting_id AND a.user_id = b.user_id AND a.id::text > b.id::text
        """
    )
    op.add_column("meeting_attendees", sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("meeting_attendees", sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("meeting_attendees", sa.Column("checkin_latitude", sa.String(), nullable=True))
    op.add_column("meeting_attendees", sa.Column("checkin_longitude", sa.String(), nullable=True))
    op.add_column("meeting_attendees", sa.Column("marked_by", sa.UUID(), nullable=True))
    op.add_column("meeting_attendees", sa.Column("reminder_24h_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("meeting_attendees", sa.Column("reminder_1h_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("meeting_attendees", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_meeting_attendees_marked_by", "meeting_attendees", "users", ["marked_by"], ["user_id"]
    )
    op.create_unique_constraint("uq_meeting_attendee", "meeting_attendees", ["meeting_id", "user_id"])
    op.create_index("ix_meeting_attendees_meeting_id", "meeting_attendees", ["meeting_id"])
    op.create_index("ix_meeting_attendees_user_id", "meeting_attendees", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_meeting_attendees_user_id", table_name="meeting_attendees")
    op.drop_index("ix_meeting_attendees_meeting_id", table_name="meeting_attendees")
    op.drop_constraint("uq_meeting_attendee", "meeting_attendees", type_="unique")
    op.drop_constraint("fk_meeting_attendees_marked_by", "meeting_attendees", type_="foreignkey")
    for column in (
        "created_at", "reminder_1h_sent_at", "reminder_24h_sent_at", "marked_by",
        "checkin_longitude", "checkin_latitude", "checked_in_at", "responded_at",
    ):
        op.drop_column("meeting_attendees", column)

    for column in ("updated_at", "attendance_finalized_at", "audience_roles", "audience", "status"):
        op.drop_column("meetings", column)

    op.execute("UPDATE employee_reports SET work_mode = 'remote' WHERE work_mode = 'online'")
    op.drop_column("employee_reports", "is_late")

    op.drop_index("uq_work_schedule_override_company_date", table_name="work_schedule_overrides")
    op.drop_index("ix_work_schedule_overrides_date", table_name="work_schedule_overrides")
    op.drop_index("ix_work_schedule_overrides_user_id", table_name="work_schedule_overrides")
    op.drop_table("work_schedule_overrides")

    op.drop_index("uq_work_schedule_company_weekday", table_name="work_schedule_days")
    op.drop_index("ix_work_schedule_days_user_id", table_name="work_schedule_days")
    op.drop_table("work_schedule_days")
