from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from common.auth_dependencies import get_current_user_id
from common.database import get_db
from .schemas import TicketCreate, TicketReply, TicketOut, TicketDetailOut, TicketMessageOut
from .service import SupportService

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
