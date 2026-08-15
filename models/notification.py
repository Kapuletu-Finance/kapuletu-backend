import uuid
from datetime import datetime
from sqlalchemy import UUID, Column, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from models.base import Base

class Notification(Base):
    __tablename__ = "notifications"

    notification_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String, nullable=False, default="system_alert")
    is_read = Column(Boolean, default=False, nullable=False)
    related_entity_id = Column(String, nullable=True) # Optional link to a transaction, campaign, etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", backref="notifications")

    __table_args__ = (
        Index("idx_notifications_user_id", "user_id"),
        Index("idx_notifications_created_at", "created_at"),
    )
