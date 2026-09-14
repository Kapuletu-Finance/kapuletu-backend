from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from .base import Base

class WhatsAppBlocklist(Base):
    __tablename__ = 'whatsapp_blocklist'

    phone_number = Column(String, primary_key=True, index=True)
    attempt_count = Column(Integer, default=1, nullable=False)
    is_blocked = Column(Boolean, default=False, nullable=False)
    last_attempt_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
