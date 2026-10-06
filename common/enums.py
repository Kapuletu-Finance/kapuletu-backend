import enum

class UserRole(str, enum.Enum):
    TREASURER = "treasurer"
    ADMIN = "admin" # Legacy generic admin, deprecated in favor of specific roles
    SUPER_ADMIN = "super_admin"
    CONTENT_MANAGER = "content_manager"
    SUPPORT_AGENT = "support_agent"
    FINANCE_MANAGER = "finance_manager"
    CEO = "ceo"

class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
