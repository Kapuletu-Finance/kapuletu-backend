"""
A person's own communication preferences (the preference centre).

Marketing is opt-in per channel. users.marketing_consent says the person agreed to marketing at all; a
marketing suppression on a channel says they turned that channel off. So:
    email on     = consent and email not suppressed for marketing
    whatsapp on  = consent and WhatsApp not suppressed for marketing
Service and security messages (receipts, sign-in codes) can't be turned off here.

Every change is written to the audit log with its source, which is the record of consent the Data Protection
Act asks us to keep.
"""
from typing import Optional

from sqlalchemy.orm import Session

from models.communications import CommSuppression
from models.users import User

from .common import CommError, audit, normalize_destination
from .consent import add_suppression, mask_email


def _suppressed(db: Session, channel: str, destination: Optional[str]) -> bool:
    if not destination:
        return True
    return db.query(CommSuppression).filter(
        CommSuppression.channel == channel, CommSuppression.destination == destination,
        CommSuppression.category.in_(("marketing", "all")),
    ).first() is not None


def get_preferences(db: Session, user: User) -> dict:
    email = normalize_destination("email", user.email)
    phone = normalize_destination("whatsapp", user.phone_number)
    consent = bool(user.marketing_consent)
    hard_blocked = db.query(CommSuppression).filter(
        CommSuppression.channel == "email", CommSuppression.destination == email, CommSuppression.category == "all",
    ).first() is not None
    return {
        "email": mask_email(user.email),
        "phone_number": f"…{phone[-3:]}" if phone else None,
        "marketing": {
            "email": consent and not _suppressed(db, "email", email),
            "whatsapp": consent and not _suppressed(db, "whatsapp", phone),
        },
        # Emails to this address bounced; marketing can't be switched on until the address is fixed
        "email_blocked": hard_blocked,
    }


def update_preferences(db: Session, user: User, email: Optional[bool] = None, whatsapp: Optional[bool] = None,
                       source: str = "preference_centre") -> dict:
    before = get_preferences(db, user)["marketing"]
    wanted = {"email": before["email"] if email is None else email,
              "whatsapp": before["whatsapp"] if whatsapp is None else whatsapp}
    destinations = {"email": normalize_destination("email", user.email),
                    "whatsapp": normalize_destination("whatsapp", user.phone_number)}

    for channel, on in wanted.items():
        destination = destinations[channel]
        if not destination:
            if on:
                raise CommError("Add an email address first" if channel == "email" else "Add a phone number first")
            continue
        if on:
            # The person opting back in themselves is the one thing that lifts an unsubscribe or spam complaint
            blocking = db.query(CommSuppression).filter(
                CommSuppression.channel == channel, CommSuppression.destination == destination,
                CommSuppression.category.in_(("marketing", "all")),
            ).all()
            if any(s.category == "all" for s in blocking):
                raise CommError("Emails to this address bounced, so it's blocked. Contact support to fix it.", 409)
            for s in blocking:
                db.delete(s)
        else:
            add_suppression(db, channel, destination, "unsubscribed", category="marketing", user_id=user.user_id,
                            note=f"Turned off in {source.replace('_', ' ')}")

    user.marketing_consent = any(wanted.values())
    db.flush()
    after = get_preferences(db, user)["marketing"]
    if after != before:
        audit(db, user.user_id, "MARKETING_PREFERENCES_CHANGED", "USER", user.user_id,
              {"from": before, "to": after, "source": source})
    db.commit()
    return get_preferences(db, user)
