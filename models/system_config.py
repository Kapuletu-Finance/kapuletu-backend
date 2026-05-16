from sqlalchemy import Column, String, JSON
from .base import Base

class SystemConfig(Base):
    """
    SystemConfig: Stores platform-wide dynamic settings.
    Used for AI training modes, maintenance flags, and global thresholds.
    """
    __tablename__ = "system_configs"

    config_key = Column(String, primary_key=True)
    config_value = Column(JSON, nullable=False)
