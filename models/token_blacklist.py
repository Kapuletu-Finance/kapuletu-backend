import datetime
import uuid
from sqlalchemy import Column, String, DateTime, UUID, ForeignKey
from .base import Base

class TokenBlacklist(Base):
    """
    Stores revoked JWT access and refresh tokens.
    Tokens in this table are considered invalid, even if they have not yet expired.
    """
    __tablename__ = "token_blacklist"

    token_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    revoked_at = Column(DateTime, default=datetime.datetime.utcnow)
