import datetime
import uuid

from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .base import Base


class Plan(Base):
    """
    Plan Model: Defines the tiers and limits of the KapuLetu service.
    
    Used to enforce feature gating and resource limits (e.g. max groups, max campaigns)
    based on the treasurer's pricing tier.
    """
    __tablename__ = "plans"

    plan_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Tier name (e.g. 'Basic', 'Professional', 'Enterprise')
    name = Column(String, unique=True, nullable=False) 
    # Resource limits
    max_groups = Column(Integer, default=1)
    max_campaigns = Column(Integer, default=5)
    max_transactions_per_month = Column(Integer, default=100)
    # Monthly cost in local currency units
    price = Column(Integer, default=0) 
    # JSON containing allowed features e.g. {"excel_exports": true}
    from sqlalchemy import JSON
    allowed_features = Column(JSON, default=dict)
class Subscription(Base):
    """
    Subscription Model: Maps a User to a specific Plan with timing constraints.
    
    Controls whether a treasurer's account is currently authorized to use 
    the system's features.
    """
    __tablename__ = "subscriptions"

    subscription_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The treasurer who owns the subscription
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    # The active tier for this subscription
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.plan_id"), nullable=False)
    # Lifecycle status (active, expired, suspended)
    status = Column(String, default="active") 
    start_date = Column(DateTime, default=datetime.datetime.utcnow)
    end_date = Column(DateTime)
    is_auto_renew = Column(Boolean, default=True)

    user = relationship("User", back_populates="subscriptions")

class UsageTracking(Base):
    """
    UsageTracking Model: Monitors real-time resource consumption against Plan limits.
    
    Used by decorators to block actions (like new ingestion or approvals) 
    if a treasurer has exceeded their monthly quota.
    """
    __tablename__ = "usage_tracking"

    usage_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The user whose usage is being tracked
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    # The metric being counted (e.g. 'monthly_transaction_count')
    metric_name = Column(String, nullable=False) 
    # The current count for the current billing cycle
    current_value = Column(Integer, default=0)
    # Timestamp when the counter was last zeroed (usually monthly)
    last_reset = Column(DateTime, default=datetime.datetime.utcnow)

class SubscriptionPayment(Base):
    """
    SubscriptionPayment Model: Detailed records of individual billing transactions.
    """
    __tablename__ = "subscription_payments"

    payment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.subscription_id"), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String, default="KES")
    status = Column(String, default="success") # success, failed, pending
    payment_method = Column(String) # mpesa, card, override
    transaction_type = Column(String, default="payment") # payment, refund, pay_in
    provider_reference = Column(String) # External ID from Safaricom/Payment Provider
    from sqlalchemy import JSON
    payment_metadata = Column(JSON, default=dict) # To store plan_id for webhooks
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
