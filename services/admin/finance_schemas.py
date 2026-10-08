from decimal import Decimal
from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field

Amount = Decimal  # KES, two decimal places


class PlanCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    code: Optional[str] = Field(None, pattern=r"^[a-z0-9_]{2,40}$", description="Stable id; defaults from the name")
    price: Amount = Field(..., ge=0, max_digits=12, decimal_places=2, description="Monthly price")
    annual_price: Optional[Amount] = Field(
        None, ge=0, max_digits=12, decimal_places=2,
        description="Defaults to monthly price x annual_months_charged",
    )
    max_groups: int = Field(1, ge=0)
    max_campaigns: int = Field(5, ge=0)
    max_transactions: int = Field(100, ge=0)
    allowed_features: Dict[str, Any] = Field(default_factory=dict)
    is_public: bool = True


class PlanUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    price: Optional[Amount] = Field(None, ge=0, max_digits=12, decimal_places=2)
    annual_price: Optional[Amount] = Field(None, ge=0, max_digits=12, decimal_places=2)
    max_groups: Optional[int] = Field(None, ge=0)
    max_campaigns: Optional[int] = Field(None, ge=0)
    max_transactions: Optional[int] = Field(None, ge=0)
    allowed_features: Optional[Dict[str, Any]] = None
    is_public: Optional[bool] = None


class BillingSettingsIn(BaseModel):
    currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")
    trial_days: Optional[int] = Field(None, ge=0, le=365)
    grace_period_days: Optional[int] = Field(None, ge=0, le=90)
    annual_months_charged: Optional[int] = Field(None, ge=1, le=12)
    addon_monthly_price: Optional[Amount] = Field(None, ge=0, max_digits=12, decimal_places=2)
    tax_rate_percent: Optional[Decimal] = Field(None, ge=0, le=100, max_digits=5, decimal_places=2)
    invoice_prefix: Optional[str] = Field(None, pattern=r"^[A-Z0-9]{2,10}$")


RefundReasonCode = Literal["duplicate", "service_issue", "billing_error", "goodwill", "other"]


class RefundIn(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    reason_code: RefundReasonCode = "other"


class SubscriptionOverrideIn(BaseModel):
    plan_id: str
    duration: int = Field(30, ge=1, le=3650, description="Days to grant")
    is_trial: bool = False
    reason: Optional[str] = Field(None, max_length=500)


class SubscriptionOverrideForUserIn(SubscriptionOverrideIn):
    user_id: str


class RefundRequestIn(BaseModel):
    payment_id: str
    reason: str = Field(..., min_length=3, max_length=500)
    reason_code: RefundReasonCode = "other"
    amount: Optional[Amount] = Field(None, gt=0, max_digits=12, decimal_places=2, description="Defaults to the full payment")


class RefundDecisionIn(BaseModel):
    note: Optional[str] = Field(None, max_length=500)


class SubscriptionActionIn(BaseModel):
    action: Literal["extend", "change_plan", "cancel"]
    reason: str = Field(..., min_length=3, max_length=500)
    days: Optional[int] = Field(None, ge=1, le=3650, description="For extend")
    plan_id: Optional[str] = Field(None, description="For change_plan")


class ReportScheduleIn(BaseModel):
    report_type: Literal["revenue", "refunds", "receivables", "payment_methods", "tax"]
    frequency: Literal["weekly", "monthly"]
    format: Literal["csv", "excel", "pdf"] = "pdf"
    recipients: List[EmailStr] = Field(..., min_length=1, max_length=20)


class ReportScheduleUpdateIn(BaseModel):
    frequency: Optional[Literal["weekly", "monthly"]] = None
    format: Optional[Literal["csv", "excel", "pdf"]] = None
    recipients: Optional[List[EmailStr]] = Field(None, min_length=1, max_length=20)
    is_active: Optional[bool] = None


class ReconciliationResolveIn(BaseModel):
    resolution: Literal["resolved", "ignored"]
    note: str = Field(..., min_length=3, max_length=500)


class FlutterwavePullIn(BaseModel):
    date_from: date = Field(..., alias="from")
    date_to: date = Field(..., alias="to")
