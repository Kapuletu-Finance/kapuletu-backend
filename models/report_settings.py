from sqlalchemy import UUID, Column, ForeignKey, String, Boolean, Integer
from sqlalchemy.orm import relationship

from .base import Base

class CampaignReportSettings(Base):
    """
    Stores custom WhatsApp template settings for a campaign.
    If a campaign doesn't have these settings, the system falls back to the Default KapuLetu Standard.
    """
    __tablename__ = "campaign_report_settings"

    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.campaign_id"), primary_key=True)
    
    header_template = Column(String, nullable=True)
    footer_template = Column(String, nullable=True)
    
    use_emojis = Column(Boolean, default=True)
    show_status_text = Column(Boolean, default=False)
    blank_slots_count = Column(Integer, default=3)
    
    # Secure PIN for the public Web Report
    public_access_pin = Column(String(4), nullable=True)
    
    campaign = relationship("Campaign")
