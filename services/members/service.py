from sqlalchemy import func
from common.utils import parse_uuid
from sqlalchemy.orm import Session
from models.transaction import Transaction

def list_members_by_group(db: Session, group_id: str):
    """
    Derives a list of unique contributors (Members) from the group's transaction history.
    Each record in the transaction table represents one member contribution.
    """
    # Group by sender name and phone to get a unique list of 'Members'
    contributors = db.query(
        Transaction.sender_phone,
        func.max(Transaction.sender_name).label("name"),
        func.count(Transaction.transaction_id).label("total_contributions"),
        func.sum(Transaction.amount).label("total_amount")
    ).filter(Transaction.group_id == parse_uuid(group_id)).group_by(Transaction.sender_phone).all()
    
    return [
        {
            "phone": c.sender_phone,
            "name": c.name,
            "count": c.total_contributions,
            "total_value": float(c.total_amount)
        } for c in contributors
    ]

def get_contributor_history(db: Session, group_id: str, phone: str):
    """
    Returns the full contribution history for a specific person in a group.
    """
    history = db.query(Transaction).filter(
        Transaction.group_id == parse_uuid(group_id),
        Transaction.sender_phone == phone
    ).order_by(Transaction.created_at.desc()).all()
    
    return [
        {
            "id": str(t.transaction_id),
            "date": t.created_at.isoformat(),
            "amount": float(t.amount),
            "code": t.transaction_code,
            "status": t.status
        } for t in history
    ]
