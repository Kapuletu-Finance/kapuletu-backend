from typing import List, Optional
from pydantic import BaseModel, Field

class SecuritySettings(BaseModel):
    require_2fa: bool = Field(False)
    two_fa_method: str = Field("SMS", description="SMS, AUTHENTICATOR, WHATSAPP")
    session_timeout_minutes: int = Field(60)
    require_pin_for_export: bool = Field(False)
    audit_log_retention_days: int = Field(30)

class AutomationSettings(BaseModel):
    auto_approve_enabled: bool = Field(False)
    confidence_threshold: float = Field(0.90)
    default_group_id: Optional[str] = Field(None)
    fallback_action: str = Field("REVIEW_INBOX", description="REVIEW_INBOX, REJECT")

class RegionalSettings(BaseModel):
    default_currency: str = Field("KES")
    timezone: str = Field("Africa/Nairobi")
    number_format: str = Field("COMMA")
    date_format: str = Field("DD/MM/YYYY")
    language: str = Field("EN")

class NotificationSettings(BaseModel):
    large_transaction_alert: bool = Field(False)
    large_transaction_threshold: float = Field(50000.0)
    alert_channels: List[str] = Field(default_factory=lambda: ["WHATSAPP"])

class ReportingSettings(BaseModel):
    auto_report_frequency: str = Field("none", description="daily, weekly, monthly, none")
    global_header_template: Optional[str] = Field(None)
    global_footer_template: Optional[str] = Field(None)
    remove_kapuletu_branding: bool = Field(False)
    use_emojis: bool = Field(True)
    public_ledger_pin: Optional[str] = Field(None)

class BillingSettings(BaseModel):
    auto_renew_subscription: bool = Field(True)
    default_payment_method: str = Field("MPESA")
    billing_email: Optional[str] = Field(None)

class UserSettings(BaseModel):
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    automation: AutomationSettings = Field(default_factory=AutomationSettings)
    regional: RegionalSettings = Field(default_factory=RegionalSettings)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    reporting: ReportingSettings = Field(default_factory=ReportingSettings)
    billing: BillingSettings = Field(default_factory=BillingSettings)

class GroupSettings(BaseModel):
    automation: Optional[AutomationSettings] = Field(None)
    reporting: Optional[ReportingSettings] = Field(None)

class CampaignSettings(BaseModel):
    reporting: Optional[ReportingSettings] = Field(None)
