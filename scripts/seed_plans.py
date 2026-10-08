import os
import sys

# Ensure backend root is in PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.database import SessionLocal
from models.subscription import Plan
from services.finance import billing

def seed_plans():
    db = SessionLocal()
    
    plans_data = [
        {
            "code": "basic",
            "name": "Basic",
            "price": 0,
            "max_groups": 1,
            "max_campaigns": 1,
            "max_transactions_per_month": 30,
            "allowed_features": {
                "whatsapp_parsing": False,
                "excel_exports": False,
                "pdf_exports": False,
                "ai_auto_approve": False
            }
        },
        {
            "code": "bronze",
            "name": "Bronze",
            "price": 500,
            "max_groups": 1,
            "max_campaigns": 3,
            "max_transactions_per_month": 50,
            "allowed_features": {
                "whatsapp_parsing": True,
                "excel_exports": False,
                "pdf_exports": True,
                "ai_auto_approve": False
            }
        },
        {
            "code": "silver",
            "name": "Silver",
            "price": 1000,
            "max_groups": 5,
            "max_campaigns": 15,
            "max_transactions_per_month": 500,
            "allowed_features": {
                "whatsapp_parsing": True,
                "excel_exports": True,
                "pdf_exports": True,
                "ai_auto_approve": True
            }
        },
        {
            "code": "gold",
            "name": "Gold",
            "price": 1500,
            "max_groups": 9999,
            "max_campaigns": 9999,
            "max_transactions_per_month": 10000,
            "allowed_features": {
                "whatsapp_parsing": True,
                "excel_exports": True,
                "pdf_exports": True,
                "ai_auto_approve": True,
                "deep_ai_insights": True
            }
        },
        {
            "code": "professional",
            "name": "Professional",
            "price": 2000,
            "max_groups": 9999,
            "max_campaigns": 9999,
            "max_transactions_per_month": 10000,
            "allowed_features": {
                "whatsapp_parsing": True,
                "excel_exports": True,
                "pdf_exports": True,
                "ai_auto_approve": True,
                "deep_ai_insights": True
            }
        }
    ]
    
    for plan_data in plans_data:
        # Check if plan exists (by code, or by name for databases seeded before plans had codes)
        existing = db.query(Plan).filter(
            (Plan.code == plan_data["code"]) | (Plan.name == plan_data["name"])
        ).first()
        if not existing:
            new_plan = Plan(
                code=plan_data["code"],
                name=plan_data["name"],
                price=plan_data["price"],
                max_groups=plan_data["max_groups"],
                max_campaigns=plan_data["max_campaigns"],
                max_transactions_per_month=plan_data["max_transactions_per_month"],
                allowed_features=plan_data["allowed_features"]
            )
            db.add(new_plan)
            print(f"Created Plan: {plan_data['name']}")
        else:
            print(f"Plan {plan_data['name']} already exists. Skipping update to preserve manual edits.")
            
    db.flush()

    # Billing rules row and an open monthly + annual price for every plan
    billing.get_settings(db)
    for plan in db.query(Plan).all():
        billing.current_price(db, plan, "month")
        billing.current_price(db, plan, "year")

    db.commit()
    db.close()
    print("Seed complete.")

if __name__ == "__main__":
    seed_plans()
