from typing import Optional

from sqlalchemy.orm import Session

from models.subscription import Plan

FREE_PLAN_CODE = "basic"
TRIAL_PLAN_CODES = ("professional", "pro")
# Names the free tier went by before plans had codes.
FREE_PLAN_NAMES = ("Basic", "Free")


def get_free_plan(db: Session) -> Optional[Plan]:
    """The tier users land on without a paid subscription."""
    plan = db.query(Plan).filter(Plan.code == FREE_PLAN_CODE).first()
    if plan:
        return plan
    for name in FREE_PLAN_NAMES:
        plan = db.query(Plan).filter(Plan.name == name).first()
        if plan:
            return plan
    return db.query(Plan).filter(Plan.price == 0).order_by(Plan.name.asc()).first()


def get_trial_plan(db: Session) -> Optional[Plan]:
    """The plan a free trial unlocks (Professional)."""
    for code in TRIAL_PLAN_CODES:
        plan = db.query(Plan).filter(Plan.code == code).first()
        if plan:
            return plan
    return None
