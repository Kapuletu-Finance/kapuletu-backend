from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_admin_user, get_verified_user, require_role
from common.enums import UserRole
from common.system_config_service import set_system_config
from models.system_config import SystemConfig
from services.documents.organization import (
    OrganizationProfile, get_organization_profile, update_organization_profile,
)

router = APIRouter(prefix="/admin", tags=["14. Admin Governance Suite"])

class ConfigUpdate(BaseModel):
    key: str
    value: Any

class ConfigUpdateRequest(BaseModel):
    configs: List[ConfigUpdate]


@router.get("/config", response_model=Dict[str, Any], summary="Get Platform Configurations")
async def get_system_config(
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(get_admin_user)
):
    configs = db.query(SystemConfig).all()
    result = {}
    for c in configs:
        result[c.config_key] = c.config_value
    return result

@router.patch("/config", summary="Update Platform Configurations")
async def update_system_config(
    payload: ConfigUpdateRequest,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(get_admin_user)
):
    for item in payload.configs:
        set_system_config(db, item.key, item.value, commit=False)
    db.commit()
    return {"message": "Configuration updated successfully"}


# --- Organisation profile (letterhead on official documents) ---

_letterhead_editor = require_role([UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.CEO])


@router.get("/organization-profile", response_model=OrganizationProfile, summary="Get Letterhead Details")
async def get_org_profile(db: Session = Depends(get_db), _: Dict[str, Any] = Depends(get_admin_user)):
    return get_organization_profile(db)


@router.put("/organization-profile", response_model=OrganizationProfile, summary="Update Letterhead Details")
async def put_org_profile(
    payload: OrganizationProfile,
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(_letterhead_editor),
):
    return update_organization_profile(db, payload)
