import uuid
from sqlalchemy import Column, String, DateTime, Integer, JSON, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
import datetime
from models.base import Base

class BroadcastCampaign(Base):
    __tablename__ = 'broadcast_campaigns'

    campaign_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    message_body = Column(String, nullable=False)
    target_audience = Column(String(50), nullable=False) # e.g. "all_members", "active_subscribers"
    channels = Column(JSONB, nullable=False) # list of channels e.g. ["email", "in_app"]
    
    status = Column(String(50), default="sent") # sent, failed, queued
    recipients_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    scheduled_for = Column(DateTime, nullable=True)
