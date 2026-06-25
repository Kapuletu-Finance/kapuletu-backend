from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from common.database import get_db
from common.auth_dependencies import get_current_user
from services.groups.schemas import GroupCreate, GroupUpdate, GroupOut
from repositories import group_repo

router = APIRouter(prefix="/groups", tags=["3. Groups Management"])

@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED, summary="Create Group")
async def create_group(
    payload: GroupCreate, 
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Creates a new community organization (Chama) owned by the current treasurer."""
    new_group = group_repo.create_group(
        db=db, 
        owner_id=current_user.get('sub'), 
        name=payload.name, 
        description=payload.description
    )
    return new_group

@router.get("", response_model=List[GroupOut], summary="Get All My Groups")
async def list_groups(
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Lists all active groups owned by the current treasurer."""
    groups = group_repo.get_owner_groups(db=db, owner_id=current_user.get('sub'))
    return groups

@router.get("/{group_id}", response_model=GroupOut, summary="Get Single Group")
async def get_group(
    group_id: str, 
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Retrieves specific details of a group."""
    group = group_repo.get_group(db=db, group_id=group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    
    # Security Check: Ensure the user actually owns this group
    if str(group.owner_id) != current_user.get('sub'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to access this group.")
        
    return group

@router.patch("/{group_id}", response_model=GroupOut, summary="Update Group")
async def update_group(
    group_id: str, 
    payload: GroupUpdate, 
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Updates group properties (Name, Description, Currency)."""
    group = group_repo.get_group(db=db, group_id=group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    
    if str(group.owner_id) != current_user.get('sub'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to modify this group.")
        
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return group
        
    updated_group = group_repo.update_group(db=db, group_id=group_id, updates=updates)
    return updated_group

@router.delete("/{group_id}", response_model=GroupOut, summary="Archive Group")
async def archive_group(
    group_id: str, 
    db: Session = Depends(get_db), 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Safely archives (soft deletes) a group, preserving historical ledger data."""
    group = group_repo.get_group(db=db, group_id=group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        
    if str(group.owner_id) != current_user.get('sub'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to archive this group.")
        
    if not group.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Group is already archived.")
        
    archived_group = group_repo.archive_group(db=db, group_id=group_id)
    return archived_group
