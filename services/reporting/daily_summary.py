from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime

from models.campaign import Campaign
from models.transaction import Transaction

def generate_summary(db: Session, owner_id: str):
    """Calculates a real-time financial summary for the treasurer dashboard."""
    total_collected = db.query(func.sum(Transaction.amount)).filter(
        Transaction.owner_id == owner_id
    ).scalar() or 0.0

    campaign_breakdown = db.query(
        Campaign.title,
        func.sum(Transaction.amount).label("total")
    ).join(Transaction, Transaction.campaign_id == Campaign.campaign_id)\
     .filter(Transaction.owner_id == owner_id)\
     .group_by(Campaign.title).all()

    return {
        "total_collected": float(total_collected),
        "campaigns": [{"title": row.title, "total": float(row.total)} for row in campaign_breakdown]
    }

def generate_campaign_whatsapp_report(db: Session, campaign_id: str, manual_instructions: str = None):
    """
    Generates a Hyper-Clean, Professional WhatsApp Contribution Report.
    Prioritizes instructions set during campaign creation.
    """
    # 1. Fetch Data
    campaign = db.query(Campaign).filter(Campaign.campaign_id == campaign_id).first()
    if not campaign:
        return "ERROR: CAMPAIGN RECORD NOT FOUND."

    txns = db.query(Transaction).filter(
        Transaction.campaign_id == campaign_id,
        Transaction.status == "approved"
    ).order_by(Transaction.created_at.asc()).all()

    # 2. Financial Context
    total_collected = sum(float(t.amount) for t in txns)
    target = float(campaign.target_amount) if campaign.target_amount else 0.0
    remaining_balance = max(0, target - total_collected)
    date_str = datetime.utcnow().strftime("%d %B %Y")
    
    # 3. Instruction Logic (Priority: Manual Override > Campaign DB > Default)
    instructions = manual_instructions or campaign.payment_instructions or "Pay via M-Pesa to the Treasury Number"

    # 4. Build the Hyper-Clean Structured Message
    report = f"KAPULETU TREASURY: {campaign.title.upper()}\n"
    report += f"STATUS REPORT AS OF {date_str.upper()}\n"
    report += f"====================================\n\n"
    
    report += f"PAYMENT INSTRUCTIONS:\n"
    report += f"{instructions}\n\n"
    
    if campaign.description:
        report += f"GOAL DESCRIPTION:\n"
        report += f"{campaign.description}\n\n"
    
    report += f"CONTRIBUTOR LIST:\n"
    report += f"------------------------------------\n"
    if not txns:
        report += f"(No approved records to display)\n"
    else:
        for i, t in enumerate(txns, 1):
            name = t.sender_name or f"Member {t.sender_phone[-4:]}" if t.sender_phone else "Member"
            report += f"{i:2}. {name:18} KES {float(t.amount):>8,.0f}\n"
    
    report += f"------------------------------------\n\n"
    
    report += f"FINANCIAL SUMMARY:\n"
    report += f"TOTAL COLLECTED:   KES {total_collected:>10,.2f}\n"
    if target > 0:
        report += f"CAMPAIGN TARGET:   KES {target:>10,.2f}\n"
        report += f"OUTSTANDING:       KES {remaining_balance:>10,.2f}\n"
    
    report += f"====================================\n\n"
    report += f"This is an automated treasury update. "
    report += f"For corrections, please contact the treasurer."

    return report
