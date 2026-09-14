from typing import Dict, Any, List
from sqlalchemy.orm import Session
from models.campaign import Campaign
from models.transaction import Transaction
from common.utils import parse_uuid
from common.config import get_config

def build_campaign_report_data(db: Session, campaign: Campaign, is_preview: bool = False) -> Dict[str, Any]:
    settings = campaign.settings_override or {}
    title = settings.get("report_title")
    if not title or title == "Campaign Update":
        title = f"{campaign.title} Update"
        
    footer = settings.get("report_footer", "")
    indicator = settings.get("paid_indicator", "\u2713")
    
    def fmt_ksh(val: float) -> str:
        return f"{val:,.0f}" if float(val).is_integer() else f"{val:,.2f}"
    
    transactions = db.query(Transaction).filter(
        Transaction.campaign_id == parse_uuid(str(campaign.campaign_id)), 
        Transaction.status == "approved"
    ).order_by(Transaction.created_at.asc()).all()
    
    raised = sum(t.amount for t in transactions)
    pm_map = {"mpesa": 0.0, "cash": 0.0, "bank": 0.0, "pledge": 0.0}
    for t in transactions:
        pm = (t.payment_method or "").lower().replace("-", "").replace(" ", "")
        if pm in pm_map:
            pm_map[pm] += float(t.amount)
        elif "mpesa" in pm:
            pm_map["mpesa"] += float(t.amount)
        elif "cash" in pm:
            pm_map["cash"] += float(t.amount)
        elif "bank" in pm:
            pm_map["bank"] += float(t.amount)
        elif "pledge" in pm:
            pm_map["pledge"] += float(t.amount)
    
    lines = []
    lines.append(f"*{title}*")
    lines.append("")
    if campaign.description:
        lines.append(campaign.description)
        lines.append("")
        
    remaining = max(0, float(campaign.target_amount) - float(raised))
    
    is_goal_met = float(campaign.target_amount) > 0 and float(raised) >= float(campaign.target_amount)
    
    if is_goal_met:
        lines.append("*Goal Achieved Update! 🌟*")
    else:
        lines.append("*Progress Update:*")
    
    if float(raised) >= float(campaign.target_amount):
        lines.append(f"So far, we have raised Ksh {fmt_ksh(raised)}, successfully surpassing our initial goal of Ksh {fmt_ksh(float(campaign.target_amount))}! Thank you to everyone who made this possible. The campaign remains open, and any further contributions are still greatly appreciated.")
    else:
        lines.append(f"So far, we have raised Ksh {fmt_ksh(raised)} against our goal of Ksh {fmt_ksh(float(campaign.target_amount))}. We have an amount remaining of Ksh {fmt_ksh(remaining)} to meet our goal. Every contribution counts.")
    
    lines.append("")
    
    if pm_map["mpesa"] > 0:
        lines.append(f"*Amount Received (M-Pesa):* Ksh {fmt_ksh(pm_map['mpesa'])}")
    if pm_map["cash"] > 0:
        lines.append(f"*Amount Received (Cash):* Ksh {fmt_ksh(pm_map['cash'])}")
    if pm_map["bank"] > 0:
        lines.append(f"*Amount Received (Bank):* Ksh {fmt_ksh(pm_map['bank'])}")
    if pm_map["pledge"] > 0:
        lines.append(f"*Amount Received (Pledge):* Ksh {fmt_ksh(pm_map['pledge'])}")
        
    if pm_map["mpesa"] > 0 or pm_map["cash"] > 0 or pm_map["bank"] > 0 or pm_map["pledge"] > 0:
        lines.append("")
        
    lines.append("To send your contributions, the payment instructions are as follows:")
    if campaign.payment_instructions:
        lines.append(f"{campaign.payment_instructions}")
    lines.append("")
    
    lines.append("*Contributions Received:*")
    
    contributors_list = []
    if not transactions and is_preview:
        dummy_contributors = [
            {"name": "Contributor A", "amount": 1000.0},
            {"name": "Contributor B", "amount": 2500.0},
            {"name": "Contributor C", "amount": 500.0},
            {"name": "Contributor D", "amount": 1500.0},
            {"name": "Contributor E", "amount": 2000.0},
            {"name": "Contributor F", "amount": 3000.0},
        ]
        for i, c in enumerate(dummy_contributors, 1):
            lines.append(f"{i}. {c['name']} - Ksh {fmt_ksh(c['amount'])} {indicator}")
        contributors_list = dummy_contributors
        start_idx = 7
    elif not transactions and not is_preview:
        lines.append("(No approved records to display)")
        start_idx = 1
    else:
        # Use actual transactions
        for i, txn in enumerate(transactions, 1):
            name = txn.sender_name or "Anonymous"
            amount = float(txn.amount)
            contributors_list.append({"name": name, "amount": amount})
            lines.append(f"{i}. {name} - Ksh {fmt_ksh(amount)} {indicator}")
        start_idx = len(transactions) + 1
        
    try:
        blank_slots = int(settings.get("blank_slots", 3))
    except (ValueError, TypeError):
        blank_slots = 3
        
    for i in range(blank_slots):
        lines.append(f"{start_idx + i}.")
        
    lines.append("")
    if is_goal_met:
        lines.append("Thank you to everyone who has contributed so far. Your overwhelming support has helped us successfully reach our goal! The campaign is still ongoing, and we encourage you to continue supporting the cause.")
    else:
        lines.append("Thank you to everyone who has contributed so far. Your continued support is greatly appreciated as we work towards our goal.")
    lines.append("")
    
    if footer:
        lines.append(footer)
        lines.append("")
        
    frontend_url = get_config().FRONTEND_URL.rstrip('/')
    short_code = campaign.short_code or campaign.campaign_id
    public_url = f"{frontend_url}/r/{short_code}"
    
    lines.append("To view a more comprehensive report, click the link below:")
    lines.append(f"{public_url}")
    if settings.get("require_pin", True) and settings.get("access_pin"):
        lines.append(f"Access PIN: {settings.get('access_pin')}")
    if not settings.get("remove_watermark", False):
        lines.append("\n*Generated via KapuLetu*")
        
    return {
        "preview_text": "\n".join(lines),
        "title": title,
        "description": campaign.description,
        "raised": float(raised),
        "target": float(campaign.target_amount),
        "total_mpesa": pm_map["mpesa"],
        "total_cash": pm_map["cash"],
        "total_bank": pm_map["bank"],
        "total_pledges": pm_map["pledge"],
        "contributors": contributors_list,
        "payment_instructions": campaign.payment_instructions,
        "footer": footer,
        "public_url": public_url
    }
