"""The organisation details printed on every official Kapuletu document (the letterhead)."""
from typing import Optional

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from common.system_config_service import get_system_config, set_system_config

ORGANIZATION_PROFILE_KEY = "organization_profile"


class OrganizationProfile(BaseModel):
    name: str = Field("Kapuletu Systems", min_length=1, max_length=120)
    tagline: Optional[str] = Field("Community treasury management", max_length=160)
    address: Optional[str] = Field("Nairobi, Kenya", max_length=200)
    phone: Optional[str] = Field("+254 143 933 472", max_length=40)
    email: Optional[EmailStr] = "info@kapuletu.co.ke"
    website: Optional[str] = Field("www.kapuletu.co.ke", max_length=120)
    registration_number: Optional[str] = Field(None, max_length=60, description="Company registration number")
    tax_pin: Optional[str] = Field(None, max_length=30, description="KRA PIN")


def get_organization_profile(db: Session) -> OrganizationProfile:
    """Stored profile merged over the defaults, so documents always have a complete letterhead."""
    stored = get_system_config(db, ORGANIZATION_PROFILE_KEY, default=None) or {}
    return OrganizationProfile(**{**OrganizationProfile().model_dump(), **stored})


def update_organization_profile(db: Session, profile: OrganizationProfile) -> OrganizationProfile:
    set_system_config(db, ORGANIZATION_PROFILE_KEY, profile.model_dump(mode="json"))
    return get_organization_profile(db)
