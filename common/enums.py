import enum

class UserRole(str, enum.Enum):
    TREASURER = "treasurer"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
