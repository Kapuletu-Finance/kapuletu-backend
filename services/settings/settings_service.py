from typing import Dict, Any, Optional, cast
from pydantic import BaseModel
from common.utils import parse_uuid
from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import HTTPException, status

from models.users import User
from models.group import Group
from models.campaign import Campaign
from models.subscription import Subscription, Plan
from services.settings.schemas import UserSettings, GroupSettings, CampaignSettings

class SettingsService:
    def __init__(self, db: Session):
        self.db = db

    def _get_active_plan(self, user_id: str) -> Plan:
        sub = self.db.execute(
            select(Subscription).where(
                Subscription.user_id == parse_uuid(user_id),
                Subscription.status == "active"
            )
        ).scalars().first()
        
        if not sub:
            # Fallback to Free Plan
            plan = self.db.execute(select(Plan).where(Plan.name == "Free")).scalars().first()
        else:
            plan = self.db.execute(select(Plan).where(Plan.plan_id == sub.plan_id)).scalars().first()
            
        if not plan:
            raise HTTPException(status_code=500, detail="Configuration Error: Plan not found")
        return plan

    def _enforce_feature_gate(self, user_id: str, feature_key: str, error_message: str):
        plan = self._get_active_plan(user_id)
        features = plan.allowed_features or {}
        if not features.get(feature_key, False):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"{error_message} Upgrade from {plan.name} to unlock this feature."
            )

    # --- Global Settings ---
    def get_global_settings(self, user_id: str) -> UserSettings:
        user = self.db.execute(select(User).where(User.user_id == parse_uuid(user_id))).scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        prefs = cast(Dict[str, Any], user.preferences or {})
        return UserSettings(**prefs)

    def update_global_domain(self, user_id: str, domain: str, updates: BaseModel) -> UserSettings:
        """
        Safely isolates the update to a specific domain (e.g. 'security') to prevent clashing.
        """
        user = self.db.execute(select(User).where(User.user_id == parse_uuid(user_id))).scalars().first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
            
        # 1. Enforce feature gates for premium fields
        update_dict = updates.model_dump(exclude_unset=True)
        
        if domain == "automation" and update_dict.get("auto_approve_enabled") is True:
            self._enforce_feature_gate(user_id, "ai_auto_approve", "AI Auto-Approve is a premium feature.")
            
        if domain == "reporting" and update_dict.get("remove_kapuletu_branding") is True:
            self._enforce_feature_gate(user_id, "whitelabeling", "White-labeling is a premium feature.")
            
        # 2. Mutate only the specific domain
        prefs = user.preferences or {}
        # We merge the existing domain preferences with the new updates
        current_domain_prefs = prefs.get(domain, {})
        current_domain_prefs.update(update_dict)
        prefs[domain] = current_domain_prefs
        
        # SQLAlchemy requires flag_modified for JSON updates
        from sqlalchemy.orm.attributes import flag_modified
        user.preferences = prefs
        flag_modified(user, "preferences")
        
        # 3. Handle external model syncing (Billing -> Subscriptions)
        if domain == "billing" and "auto_renew_subscription" in update_dict:
            sub = self.db.execute(
                select(Subscription).where(
                    Subscription.user_id == parse_uuid(user_id),
                    Subscription.status == "active"
                )
            ).scalars().first()
            if sub:
                sub.is_auto_renew = update_dict["auto_renew_subscription"]
                
        self.db.commit()
        return self.get_global_settings(user_id)

    # --- Group Settings ---
    def get_group_settings(self, user_id: str, group_id: str) -> GroupSettings:
        group = self.db.execute(
            select(Group).where(Group.group_id == group_id, Group.owner_id == parse_uuid(user_id))
        ).scalars().first()
        
        if not group:
            raise HTTPException(status_code=404, detail="Group not found or access denied")
        prefs = cast(Dict[str, Any], group.settings_override or {})
        return GroupSettings(**prefs)

    def update_group_domain(self, user_id: str, group_id: str, domain: str, updates: BaseModel) -> GroupSettings:
        group = self.db.execute(
            select(Group).where(Group.group_id == group_id, Group.owner_id == parse_uuid(user_id))
        ).scalars().first()
        
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
            
        update_dict = updates.model_dump(exclude_unset=True)
        
        if domain == "automation" and update_dict.get("auto_approve_enabled") is True:
            self._enforce_feature_gate(user_id, "ai_auto_approve", "AI Auto-Approve is a premium feature.")
        if domain == "reporting" and update_dict.get("remove_kapuletu_branding") is True:
            self._enforce_feature_gate(user_id, "whitelabeling", "White-labeling is a premium feature.")

        prefs = cast(Dict[str, Any], group.settings_override or {})
        current_domain_prefs = prefs.get(domain, {})
        current_domain_prefs.update(update_dict)
        prefs[domain] = current_domain_prefs
        
        group.settings_override = prefs
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(group, "settings_override")
        
        self.db.commit()
        return self.get_group_settings(user_id, group_id)

    # --- Campaign Settings ---
    def get_campaign_settings(self, user_id: str, campaign_id: str) -> CampaignSettings:
        # Join to ensure owner has access
        campaign = self.db.execute(
            select(Campaign).join(Group).where(
                Campaign.campaign_id == campaign_id,
                Group.owner_id == parse_uuid(user_id)
            )
        ).scalars().first()
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found or access denied")
        prefs = cast(Dict[str, Any], campaign.settings_override or {})
        return CampaignSettings(**prefs)
        
    def update_campaign_domain(self, user_id: str, campaign_id: str, domain: str, updates: BaseModel) -> CampaignSettings:
        campaign = self.db.execute(
            select(Campaign).join(Group).where(
                Campaign.campaign_id == campaign_id,
                Group.owner_id == parse_uuid(user_id)
            )
        ).scalars().first()
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
            
        update_dict = updates.model_dump(exclude_unset=True)
        
        if domain == "reporting" and update_dict.get("remove_kapuletu_branding") is True:
            self._enforce_feature_gate(user_id, "whitelabeling", "White-labeling is a premium feature.")

        prefs = cast(Dict[str, Any], campaign.settings_override or {})
        current_domain_prefs = prefs.get(domain, {})
        current_domain_prefs.update(update_dict)
        prefs[domain] = current_domain_prefs
        
        campaign.settings_override = prefs
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(campaign, "settings_override")
        
        self.db.commit()
        return self.get_campaign_settings(user_id, campaign_id)

    # --- Hierarchical Resolution Engine ---
    def resolve_setting(self, user_id: str, domain: str, key: str, group_id: Optional[str] = None, campaign_id: Optional[str] = None) -> Any:
        """
        Resolves a setting value based on the Campaign > Group > Global hierarchy.
        """
        # 1. Check Campaign
        if campaign_id:
            campaign = self.db.execute(select(Campaign).where(Campaign.campaign_id == campaign_id)).scalars().first()
            if campaign and campaign.settings_override:
                val = campaign.settings_override.get(domain, {}).get(key)
                if val is not None:
                    return val
                    
        # 2. Check Group
        if group_id:
            group = self.db.execute(select(Group).where(Group.group_id == group_id)).scalars().first()
            if group and group.settings_override:
                val = group.settings_override.get(domain, {}).get(key)
                if val is not None:
                    return val
                    
        # 3. Check Global User
        user = self.db.execute(select(User).where(User.user_id == parse_uuid(user_id))).scalars().first()
        if user and user.preferences:
            val = user.preferences.get(domain, {}).get(key)
            if val is not None:
                return val
                
        # 4. Fallback to System Default (via Pydantic Model)
        user_defaults = UserSettings().model_dump()
        return user_defaults.get(domain, {}).get(key)
