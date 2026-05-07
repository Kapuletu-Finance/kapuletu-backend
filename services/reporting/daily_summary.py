from sqlalchemy import func
from sqlalchemy.orm import Session
from models.transaction import Transaction
from models.campaign import Campaign

def generate_summary(db: Session, owner_id: str):
    """
    Calculates a real-time financial summary for a treasurer.
    
    This performs aggregations on the Transaction table to find:
    - Total collected across all groups.
    - Breakdown by campaign.
    - Transaction count.
    """
    # 1. Total across all groups owned by this treasurer
    total_collected = db.query(func.sum(Transaction.amount)).filter(
        Transaction.owner_id == owner_id
    ).scalar() or 0.0

    # 2. Breakdown by Campaign
    campaign_breakdown = db.query(
        Campaign.title,
        func.sum(Transaction.amount).label("total")
    ).join(Transaction, Transaction.campaign_id == Campaign.campaign_id)\
     .filter(Transaction.owner_id == owner_id)\
     .group_by(Campaign.title).all()

    # 3. Transaction Count
    transaction_count = db.query(Transaction).filter(
        Transaction.owner_id == owner_id
    ).count()

    return {
        "total_collected": float(total_collected),
        "transaction_count": transaction_count,
        "campaigns": [
            {"title": row.title, "total": float(row.total)} for row in campaign_breakdown
        ]
    }
