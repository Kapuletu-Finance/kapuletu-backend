from typing import Dict, Any, List
from sqlalchemy.orm import Session
from models.campaign import Campaign
from models.transaction import Transaction
from common.utils import parse_uuid
from common.config import get_config

def process_template(template: str, campaign: Campaign, raised: float) -> str:
    if not template:
        return ""
    def fmt_ksh(val: float) -> str:
        return f"{val:,.0f}" if float(val).is_integer() else f"{val:,.2f}"
    
    target = float(campaign.target_amount) if campaign.target_amount else 0.0
    remaining = max(0.0, target - raised)

    res = template
    res = res.replace("[Campaign Name]", campaign.title or "")
    res = res.replace("[Campaign Description]", campaign.description or "")
    res = res.replace("[Total Raised]", fmt_ksh(raised))
    res = res.replace("[Target Amount]", fmt_ksh(target))
    res = res.replace("[Amount Remaining]", fmt_ksh(remaining))
    res = res.replace("[Payment Instructions]", campaign.payment_instructions or "")
    return res

def build_campaign_report_data(db: Session, campaign: Campaign, is_preview: bool = False) -> Dict[str, Any]:
    settings = campaign.settings_override or {}
    title = settings.get("report_title")
    if not title or title == "Campaign Update":
        title = f"*[Campaign Name]*\n\n[Campaign Description]"
        
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
    
    processed_title = process_template(title, campaign, raised)
    if processed_title:
        lines.append(processed_title)
        lines.append("")
        
    lines.append("The following are the contributions received so far:")
    
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
    
    processed_footer = process_template(footer, campaign, raised)
    if processed_footer:
        lines.append(processed_footer)
        
    frontend_url = get_config().FRONTEND_URL.rstrip('/')
    short_code = campaign.short_code or campaign.campaign_id
    public_url = f"{frontend_url}/r/{short_code}"
        
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
