from typing import List, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from common.database import get_db
from common.auth_dependencies import get_verified_user
from services.groups.schemas import GroupCreate, GroupUpdate, GroupOut, PaginatedGroupResponse
from services.auth.router import limiter
from repositories import group_repo

router = APIRouter(prefix="/groups", tags=["4. Groups Management"])

@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED, summary="Create Group")
@limiter.limit("50/minute")
async def create_group(
    request: Request,
    payload: GroupCreate, 
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Creates a new community organization or fund owned by the current treasurer."""
    try:
        new_group = group_repo.create_group(
            db=db, 
            owner_id=current_user.get('sub'), 
            name=payload.name, 
            description=payload.description,
            currency=payload.currency.value
        )
        return new_group
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Could not create group. Please ensure your user profile is fully synchronized."
        )

@router.get("", response_model=PaginatedGroupResponse, summary="Get All My Groups")
@limiter.limit("50/minute")
async def list_groups(
    request: Request,
    skip: int = Query(0, ge=0, description="Pagination skip"),
    limit: int = Query(10, ge=1, le=100, description="Pagination limit"),
    search: str = Query(None, description="Search group by name"),
    group_status: str = Query(None, description="active, archived, or all"),
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Lists all groups owned by the current treasurer with pagination, search, and stats."""
    groups = group_repo.get_owner_groups(db=db, owner_id=current_user.get('sub'), skip=skip, limit=limit, search=search, status=group_status)
    return groups

@router.get("/{group_id}", response_model=GroupOut, summary="Get Single Group")
async def get_group(
    group_id: UUID, 
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Retrieves specific details of a group."""
    group = group_repo.get_group(db=db, group_id=str(group_id))
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    
    # Security Check: Ensure the user actually owns this group
    if str(group.owner_id) != current_user.get('sub'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this group.")
        
    return group

@router.patch("/{group_id}", response_model=GroupOut, summary="Update Group")
async def update_group(
    group_id: UUID, 
    payload: GroupUpdate, 
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Updates group properties (Name, Description). Currency is immutable."""
    group = group_repo.get_group(db=db, group_id=str(group_id))
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    
    if str(group.owner_id) != current_user.get('sub'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to modify this group.")
        
    if not group.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify an archived group.")
        
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return group
        
    updated_group = group_repo.update_group(db=db, group_id=str(group_id), updates=updates)
    return updated_group

@router.patch("/{group_id}/favorite", response_model=GroupOut, summary="Toggle Favorite Group")
async def toggle_favorite_group(
    group_id: UUID, 
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Toggles the is_favorite status of a group for the current treasurer."""
    group = group_repo.get_group(db=db, group_id=str(group_id))
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    
    if str(group.owner_id) != current_user.get('sub'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to modify this group.")
        
    updated_group = group_repo.update_group(db=db, group_id=str(group_id), updates={"is_favorite": not group.is_favorite})
    return updated_group

@router.delete("/{group_id}", response_model=GroupOut, summary="Archive Group")
async def archive_group(
    group_id: UUID, 
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    """Safely archives (soft deletes) a group, preserving historical ledger data."""
    group = group_repo.get_group(db=db, group_id=str(group_id))
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        
    if str(group.owner_id) != current_user.get('sub'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to archive this group.")
        
    if not group.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group is already archived.")
        
    archived_group = group_repo.archive_group(db=db, group_id=str(group_id))
    return archived_group
