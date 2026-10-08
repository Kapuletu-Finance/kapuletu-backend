"""Human-readable labels for HR values, used in documents and emails."""

DAY_MODE_LABELS = {"physical": "Physical", "online": "Online", "off": "Off"}

ATTENDANCE_STATUS_LABELS = {
    "present": "Present",
    "late": "Late",
    "absent": "Absent",
    "excused": "Excused",
    "off": "Off",
    "upcoming": "Upcoming",
}


def format_role(role: str) -> str:
    """'support_agent' -> 'Support Agent'."""
    return role.replace("_", " ").title()
