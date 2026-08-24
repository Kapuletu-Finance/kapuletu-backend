from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any
from common.auth_dependencies import get_verified_user
from common.database import get_db
from .schemas import TicketCreate, TicketReply, TicketRatingCreate, TicketOut, TicketDetailOut, TicketMessageOut
from .service import SupportService

def get_current_user_id(current_user: Dict[str, Any] = Depends(get_verified_user)) -> str:
    return current_user.get('sub')


router = APIRouter(prefix="/support", tags=["Support"])

@router.post("/tickets", response_model=TicketOut)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = SupportService(db)
    ticket = svc.create_ticket(
        user_id=user_id,
        subject=payload.subject,
        message=payload.message,
        category=payload.category,
        priority=payload.priority
    )
    return ticket

@router.get("/tickets", response_model=list[TicketOut])
def list_tickets(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = SupportService(db)
    return svc.list_user_tickets(user_id)

@router.get("/tickets/{ticket_id}", response_model=TicketDetailOut)
def get_ticket(ticket_id: str, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = SupportService(db)
    ticket, messages = svc.get_ticket_details(user_id, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    # We construct the detail object manually or rely on ORM mode
    # For simplicity, we can modify the ticket object or let Pydantic handle it
    ticket.messages = messages
    return ticket

@router.post("/tickets/{ticket_id}/reply", response_model=TicketMessageOut)
def reply_ticket(ticket_id: str, payload: TicketReply, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    svc = SupportService(db)
    try:
        msg = svc.reply_to_ticket(user_id, ticket_id, payload.message)
        return msg
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/tickets/{ticket_id}/rate", status_code=201)
def rate_ticket(ticket_id: str, payload: TicketRatingCreate, db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    """Submit a post-session satisfaction rating for a resolved support ticket."""
    svc = SupportService(db)
    rating, err = svc.rate_ticket(
        user_id=user_id,
        ticket_id=ticket_id,
        issue_resolved=payload.issue_resolved,
        satisfaction_level=payload.satisfaction_level,
        response_quality=payload.response_quality,
        response_speed=payload.response_speed,
        comment=payload.comment,
    )
    if err == "not_found":
        raise HTTPException(status_code=404, detail="Ticket not found")
    if err == "forbidden":
        raise HTTPException(status_code=403, detail="Not your ticket")
    if err == "already_rated":
        raise HTTPException(status_code=409, detail="This session has already been rated")
    return {"message": "Thank you for your feedback! Your rating has been recorded.", "rating_id": str(rating.rating_id)}
