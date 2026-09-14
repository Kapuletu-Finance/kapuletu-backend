from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_verified_user
from services.settings.settings_service import SettingsService
from services.settings.schemas import (
    UserSettings, GroupSettings, CampaignSettings,
    SecuritySettings, AutomationSettings, RegionalSettings,
    NotificationSettings, ReportingSettings, BillingSettings
)

router = APIRouter()

# --- 1. Global User Settings ---

@router.get("/me", response_model=UserSettings, summary="Fetch Global Settings")
async def get_my_settings(
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.get_global_settings(current_user.get("sub"))

@router.put("/me/security/2fa", response_model=UserSettings, summary="Toggle 2FA")
async def update_security_2fa(
    payload: SecuritySettings, 
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_global_domain(current_user.get("sub"), "security", payload)

@router.put("/me/security/timeout", response_model=UserSettings, summary="Set Session Timeout")
async def update_security_timeout(
    payload: SecuritySettings,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_global_domain(current_user.get("sub"), "security", payload)

@router.put("/me/automation/auto-approve", response_model=UserSettings, summary="Toggle Auto Approve")
async def update_automation_approval(
    payload: AutomationSettings,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_global_domain(current_user.get("sub"), "automation", payload)

@router.put("/me/automation/fallback", response_model=UserSettings, summary="Set Fallback Routing")
async def update_automation_fallback(
    payload: AutomationSettings,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_global_domain(current_user.get("sub"), "automation", payload)

@router.put("/me/reports/frequency", response_model=UserSettings, summary="Set Auto-Report Frequency")
async def update_report_frequency(
    payload: ReportingSettings,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_global_domain(current_user.get("sub"), "reporting", payload)

@router.put("/me/reports/branding", response_model=UserSettings, summary="Set Headers and Footers")
async def update_report_branding(
    payload: ReportingSettings,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_global_domain(current_user.get("sub"), "reporting", payload)

@router.put("/me/regional/localization", response_model=UserSettings, summary="Set Localization")
async def update_localization(
    payload: RegionalSettings,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_global_domain(current_user.get("sub"), "regional", payload)

@router.put("/me/notifications/alerts", response_model=UserSettings, summary="Set Large Transaction Alerts")
async def update_alerts(
    payload: NotificationSettings,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_global_domain(current_user.get("sub"), "notifications", payload)

@router.put("/me/billing", response_model=UserSettings, summary="Toggle Auto-Renew & Payment Settings")
async def update_billing(
    payload: BillingSettings,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_global_domain(current_user.get("sub"), "billing", payload)

# --- 2. Group Level Settings ---

@router.get("/groups/{group_id}", response_model=GroupSettings, summary="Fetch Group Overrides")
async def get_group_settings_route(
    group_id: str,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.get_group_settings(current_user.get("sub"), group_id)

@router.put("/groups/{group_id}/reports", response_model=GroupSettings, summary="Override Group Reports")
async def update_group_reports(
    group_id: str,
    payload: ReportingSettings,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_group_domain(current_user.get("sub"), group_id, "reporting", payload)
    
@router.put("/groups/{group_id}/automation", response_model=GroupSettings, summary="Override Group Automation")
async def update_group_automation(
    group_id: str,
    payload: AutomationSettings,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_group_domain(current_user.get("sub"), group_id, "automation", payload)


# --- 3. Campaign Level Settings ---

@router.get("/campaigns/{campaign_id}", response_model=CampaignSettings, summary="Fetch Campaign Overrides")
async def get_campaign_settings_route(
    campaign_id: str,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.get_campaign_settings(current_user.get("sub"), campaign_id)

@router.put("/campaigns/{campaign_id}/reports", response_model=CampaignSettings, summary="Override Campaign Reports")
async def update_campaign_reports(
    campaign_id: str,
    payload: ReportingSettings,
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    service = SettingsService(db)
    return service.update_campaign_domain(current_user.get("sub"), campaign_id, "reporting", payload)
