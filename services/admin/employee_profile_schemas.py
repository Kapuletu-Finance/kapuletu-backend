from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from common.enums import UserRole
from common.permissions import PERMISSION_IDS

ActivityView = Literal["performed", "received", "logins"]


class PermissionOut(BaseModel):
    id: str
    label: str
    areas: list[str]


class EmployeeProfileOut(BaseModel):
    user_id: UUID
    first_name: str
    last_name: str
    email: str
    phone_number: Optional[str]
    role: str
    permissions: list[str]
    is_active: bool
    created_at: Optional[datetime]
    last_login_at: Optional[datetime]
    last_active_at: Optional[datetime]
    # Page the employee was last on (from the app heartbeat)
    current_action: Optional[str]
    two_factor_enabled: bool
    sessions_revoked_at: Optional[datetime]
    reports_pending: int
    reports_confirmed: int


class EmployeeUpdateIn(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=80)
    last_name: Optional[str] = Field(None, min_length=1, max_length=80)
    phone_number: Optional[str] = Field(None, min_length=7, max_length=20)
    role: Optional[str] = Field(None, min_length=2, max_length=40, pattern=r"^[a-z][a-z0-9_]*$")
    permissions: Optional[list[str]] = None

    @field_validator("role")
    @classmethod
    def _internal_role(cls, role: Optional[str]):
        if role == UserRole.TREASURER.value:
            raise ValueError("Employees can't be given the treasurer role")
        return role

    @field_validator("permissions")
    @classmethod
    def _known_permissions(cls, permissions: Optional[list[str]]):
        if permissions is None:
            return None
        unknown = sorted(set(permissions) - PERMISSION_IDS)
        if unknown:
            raise ValueError(f"Unknown permissions: {', '.join(unknown)}")
        return sorted(set(permissions))


class ActivityItemOut(BaseModel):
    id: str
    at: datetime
    action: str
    message: str
    actor_id: Optional[UUID]
    actor_name: Optional[str]


class ActivityPageOut(BaseModel):
    items: list[ActivityItemOut]
    total: int
    page: int
    limit: int
