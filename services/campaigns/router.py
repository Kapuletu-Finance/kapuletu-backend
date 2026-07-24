from typing import List, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_verified_user
from services.campaigns.schemas import CampaignCreate, CampaignUpdate, CampaignOut, PaginatedCampaignResponse
from services.auth.router import limiter
from repositories import campaign_repo, group_repo

router = APIRouter(prefix="", tags=["5. Campaigns Management"])

def _verify_group_ownership(db: Session, group_id: str, owner_id: str):
    """Helper to verify that the group exists and belongs to the current user."""
    group = group_repo.get_group(db=db, group_id=group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    if str(group.owner_id) != owner_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to manage campaigns for this group.")
    return group


@router.post("/groups/{group_id}/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED, summary="Create Campaign")
@limiter.limit("50/minute")
async def create_campaign(
    request: Request,
    group_id: UUID,
    payload: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Creates a new campaign for a specific group."""
    _verify_group_ownership(db, str(group_id), current_user.get('sub'))
    
    new_campaign = campaign_repo.create_campaign(
        db=db,
        group_id=str(group_id),
        title=payload.title,
        description=payload.description,
        target_amount=payload.target_amount,
        payment_instructions=payload.payment_instructions
    )
    return new_campaign

@router.get("/groups/{group_id}/campaigns", response_model=PaginatedCampaignResponse, summary="List Campaigns")
@limiter.limit("50/minute")
async def list_campaigns(
    request: Request,
    group_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    search: str = Query(None, description="Search by title"),
    campaign_status: str = Query(None, description="active, archived, or all"),
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Lists all campaigns for a specific group with pagination, search, and dynamic stats."""
    _verify_group_ownership(db, str(group_id), current_user.get('sub'))
    
    campaigns = campaign_repo.get_group_campaigns(db=db, group_id=str(group_id), skip=skip, limit=limit, search=search, status=campaign_status)
    return campaigns

@router.get("/campaigns/{campaign_id}", response_model=CampaignOut, summary="Get Campaign")
async def get_campaign(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Retrieves details of a specific campaign."""
    campaign = campaign_repo.get_campaign(db=db, campaign_id=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
        
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    return campaign

@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut, summary="Update Campaign")
async def update_campaign(
    campaign_id: UUID,
    payload: CampaignUpdate,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Updates campaign details."""
    campaign = campaign_repo.get_campaign(db=db, campaign_id=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
        
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    if not campaign.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify an archived campaign.")
        
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return campaign
        
    updated_campaign = campaign_repo.update_campaign(db=db, campaign_id=str(campaign_id), updates=updates)
    return updated_campaign

@router.delete("/campaigns/{campaign_id}", response_model=CampaignOut, summary="Archive Campaign")
async def archive_campaign(
    campaign_id: UUID,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Safely archives (soft deletes) a campaign."""
    campaign = campaign_repo.get_campaign(db=db, campaign_id=str(campaign_id))
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
        
    _verify_group_ownership(db, str(campaign.group_id), current_user.get('sub'))
    
    if not campaign.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign is already archived.")
        
    archived_campaign = campaign_repo.archive_campaign(db=db, campaign_id=str(campaign_id))
    return archived_campaign
