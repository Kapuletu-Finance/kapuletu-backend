from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_verified_user
from models.system_config import SystemConfig

router = APIRouter(prefix="/admin", tags=["14. Admin Governance Suite"])

class ConfigUpdate(BaseModel):
    key: str
    value: Any

class ConfigUpdateRequest(BaseModel):
    configs: List[ConfigUpdate]

def verify_admin(current_user: Dict[str, Any] = Depends(get_verified_user)):
    role = current_user.get("role")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user

@router.get("/config", response_model=Dict[str, Any], summary="Get Platform Configurations")
async def get_system_config(
    db: Session = Depends(get_db),
    _: Dict[str, Any] = Depends(verify_admin)
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
    _: Dict[str, Any] = Depends(verify_admin)
):
    for item in payload.configs:
        config = db.query(SystemConfig).filter(SystemConfig.config_key == item.key).first()
        if config:
            config.config_value = item.value
        else:
            new_config = SystemConfig(config_key=item.key, config_value=item.value)
            db.add(new_config)
    
    db.commit()
    return {"message": "Configuration updated successfully"}
