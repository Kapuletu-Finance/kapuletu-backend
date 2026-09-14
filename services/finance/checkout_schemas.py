from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime

class PlanOut(BaseModel):
    id: str
    name: str
    price: float
    limits: Dict[str, Any]

class SubscriptionUsage(BaseModel):
    groups: str
    campaigns: str

class MySubscriptionOut(BaseModel):
    active_plan: str
    is_on_trial: bool
    has_used_trial: bool = False
    days_remaining: int
    expiry_date: Optional[str]
    usage: SubscriptionUsage
    allowed_features: Dict[str, bool] = Field(default_factory=dict)

class CheckoutIn(BaseModel):
    plan_id: str
    provider: str = Field(..., description="mpesa or flutterwave")
    phone_number: Optional[str]
    email: Optional[str]
    name: Optional[str]
    billing_cycle: str = Field("monthly", description="monthly or annual")
    has_addons: bool = Field(False, description="Whether the user selected addons")

class CheckoutOut(BaseModel):
    checkout_id: str
    status: str
    provider_response: Any

class PaymentStatusOut(BaseModel):
    status: str
    confirmed_at: Optional[str]
    plan: Optional[str]

class BillingHistoryOut(BaseModel):
    payment_id: str
    amount: float
    currency: str
    status: str
    payment_method: Optional[str]
    provider_reference: Optional[str]
    created_at: datetime
