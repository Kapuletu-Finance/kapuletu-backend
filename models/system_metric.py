import datetime
import uuid
from sqlalchemy import UUID, Column, DateTime, Float, Integer
from .base import Base

class SystemMetric(Base):
    """
    SystemMetric Model: Stores rolling health metrics and response times.
    Useful for populating the performance dashboard.
    """
    __tablename__ = "system_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    cpu_percent = Column(Float, nullable=False, default=0.0)
    memory_percent = Column(Float, nullable=False, default=0.0)
    
    # Store aggregated request stats for the minute
    request_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    avg_response_time_ms = Column(Float, nullable=False, default=0.0)
    active_sessions_count = Column(Integer, nullable=False, default=0)
