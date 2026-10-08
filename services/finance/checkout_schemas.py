from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime

class PlanOut(BaseModel):
    id: str
    code: str
    name: str
    # Monthly price; kept for older clients. Same as monthly_price.
    price: float
    monthly_price: float
    annual_price: float
    currency: str
    limits: Dict[str, Any]
    allowed_features: Dict[str, Any] = Field(default_factory=dict)

class PricingConfigOut(BaseModel):
    currency: str
    trial_days: int
    annual_months_charged: int
    addon_monthly_price: float
    tax_rate_percent: float

class QuoteIn(BaseModel):
    plan_id: str
    billing_cycle: str = Field("monthly", description="monthly or annual")
    has_addons: bool = False

class QuoteLineOut(BaseModel):
    kind: str
    description: str
    quantity: int
    unit_amount: float
    amount: float

class QuoteOut(BaseModel):
    plan_id: str
    plan_name: str
    billing_cycle: str
    has_addons: bool
    currency: str
    lines: List[QuoteLineOut]
    subtotal: float
    tax_rate_percent: float
    tax: float
    total: float

class SubscriptionUsage(BaseModel):
    groups: str
    campaigns: str
    # Approved contributions this calendar month against the plan's monthly limit
    transactions: Optional[str] = None

class MySubscriptionOut(BaseModel):
    active_plan: str
    is_on_trial: bool
    has_used_trial: bool = False
    days_remaining: int
    expiry_date: Optional[str]
    usage: SubscriptionUsage
    allowed_features: Dict[str, bool] = Field(default_factory=dict)
    plan_code: Optional[str] = None
    # Plans don't renew by themselves yet (no saved card / M-Pesa standing order); users pay each period.
    renews_automatically: bool = False

class InvoiceLineOut(BaseModel):
    description: str
    quantity: int
    amount: float

class InvoiceOut(BaseModel):
    invoice_id: str
    number: str
    status: str
    currency: str
    subtotal: float
    tax: float
    total: float
    billing_cycle: Optional[str]
    period_start: Optional[datetime]
    period_end: Optional[datetime]
    issued_at: datetime
    paid_at: Optional[datetime]
    lines: List[InvoiceLineOut]

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
    transaction_type: Optional[str] = None
    invoice_number: Optional[str] = None
    plan_name: Optional[str] = None
