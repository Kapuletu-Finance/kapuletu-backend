"""
Backfill the billing tables from historical subscription payments.

    python scripts/backfill_billing.py            # dry run: prints what would change, writes nothing
    python scripts/backfill_billing.py --apply    # writes it

What it does (idempotent; rows already backfilled are skipped):
  1. Each successful paid payment without an invoice gets a paid invoice and a ledger posting
     (debit cash, credit revenue) dated when the payment was made.
  2. Each zero-value admin grant is re-labelled transaction_type = 'comp'.
  3. Each legacy refund (negative payment) gets a refunds row, a credit note on the original invoice
     and a ledger posting (debit refunds, credit cash).
  4. Trials are flagged on subscriptions, and every subscription without history gets a 'migrated' event.

Run it on a copy of production first and have finance sign off the before / after totals it prints.
"""
import argparse
import datetime
import os
import sys
from decimal import Decimal

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from common.database import SessionLocal
from common.utils import parse_uuid
from models.billing import CreditNote, Invoice, InvoiceLine, LedgerEntry, Refund, SubscriptionEvent
from models.subscription import Plan, Subscription, SubscriptionPayment
from models.users import User
from services.finance import billing
from services.finance.plans import TRIAL_PLAN_CODES


def _plan_for(db, payment):
    plan_id = (payment.payment_metadata or {}).get("plan_id")
    if plan_id:
        try:
            plan = db.get(Plan, parse_uuid(plan_id))
            if plan:
                return plan
        except ValueError:
            pass
    sub = db.get(Subscription, payment.subscription_id) if payment.subscription_id else None
    return db.get(Plan, sub.plan_id) if sub else None


def _totals(db) -> dict:
    paid = db.query(func.coalesce(func.sum(SubscriptionPayment.amount), 0)).filter(
        SubscriptionPayment.status == "success", SubscriptionPayment.amount > 0
    ).scalar()
    refunded = db.query(func.coalesce(func.sum(SubscriptionPayment.amount), 0)).filter(
        SubscriptionPayment.status == "success", SubscriptionPayment.amount < 0
    ).scalar()

    def ledger(account, side):
        col = LedgerEntry.debit if side == "debit" else LedgerEntry.credit
        return db.query(func.coalesce(func.sum(col), 0)).filter(LedgerEntry.account == account).scalar()

    return {
        "payments_received": billing.money(paid),
        "payments_refunded": billing.money(-Decimal(str(refunded))),
        "ledger_cash_net": billing.money(ledger("cash", "debit") - ledger("cash", "credit")),
        "ledger_revenue": billing.money(ledger("revenue", "credit")),
        "ledger_tax_payable": billing.money(ledger("tax_payable", "credit")),
        "ledger_refunds": billing.money(ledger("refunds", "debit")),
        "invoices": db.query(func.count(Invoice.invoice_id)).scalar(),
        "refund_rows": db.query(func.count(Refund.refund_id)).scalar(),
    }


def backfill(db) -> dict:
    counts = {"invoices": 0, "comps": 0, "refunds": 0, "orphan_refunds": 0, "trials": 0, "events": 0, "skipped": 0}
    payments = db.query(SubscriptionPayment).order_by(SubscriptionPayment.created_at.asc()).all()

    for p in payments:
        kind = p.transaction_type or "payment"
        amount = billing.money(p.amount)

        # 2. Zero-value admin grants
        if p.status == "success" and kind == "payment" and (p.payment_method == "admin_override" or amount == 0):
            p.transaction_type = "comp"
            counts["comps"] += 1
            continue

        # 1. Paid payments -> invoice + ledger
        if p.status == "success" and kind == "payment" and amount > 0:
            if p.invoice_id is None:
                plan = _plan_for(db, p)
                cycle = (p.payment_metadata or {}).get("billing_cycle") or "monthly"
                issued = p.created_at or datetime.datetime.utcnow()
                invoice = Invoice(
                    number=billing.next_invoice_number(db, issued), user_id=p.user_id,
                    subscription_id=p.subscription_id, status="paid", currency=p.currency or "KES",
                    subtotal=amount, tax=0, total=amount, billing_cycle=cycle,
                    period_start=issued, period_end=issued + datetime.timedelta(days=365 if cycle == "annual" else 30),
                    issued_at=issued, due_at=issued, paid_at=issued, notes="Backfilled from payment history",
                )
                db.add(invoice)
                db.flush()
                db.add(InvoiceLine(
                    invoice_id=invoice.invoice_id, kind="plan",
                    description=f"{plan.name if plan else 'Subscription'} plan ({cycle})",
                    quantity=1, unit_amount=amount, amount=amount, plan_id=plan.plan_id if plan else None,
                ))
                p.invoice_id = invoice.invoice_id
                counts["invoices"] += 1
            invoice = db.get(Invoice, p.invoice_id)
            billing.post_payment(db, p, invoice, p.created_at)
            continue

        # 3. Legacy refunds
        if p.status == "success" and kind == "refund" and amount < 0:
            if db.query(Refund).filter(Refund.refund_payment_id == p.payment_id).first():
                continue
            original_id = (p.payment_metadata or {}).get("original_payment_id")
            original = db.get(SubscriptionPayment, parse_uuid(original_id)) if original_id else None
            if original is None:
                counts["orphan_refunds"] += 1
                continue
            refund = Refund(
                payment_id=original.payment_id, invoice_id=original.invoice_id, user_id=p.user_id, amount=-amount,
                currency=p.currency or "KES", reason_code="other", reason=(p.payment_metadata or {}).get("reason"),
                status="approved", requested_at=p.created_at, decided_at=p.created_at, refund_payment_id=p.payment_id,
            )
            db.add(refund)
            db.flush()
            if original.invoice_id:
                db.add(CreditNote(
                    number=billing.next_credit_note_number(db, p.created_at), invoice_id=original.invoice_id,
                    user_id=p.user_id, refund_id=refund.refund_id, amount=-amount, currency=refund.currency,
                    reason=refund.reason, issued_at=p.created_at,
                ))
            meta = dict(original.payment_metadata or {})
            meta.setdefault("refund_payment_id", str(p.payment_id))
            meta["refund_id"] = str(refund.refund_id)
            original.payment_metadata = meta
            billing.post_refund(db, refund, p.created_at)
            counts["refunds"] += 1
            continue

        counts["skipped"] += 1  # pending / failed attempts carry no money

    # 4. Trials and baseline history
    trial_plan_ids = {p.plan_id for p in db.query(Plan).filter(Plan.code.in_(TRIAL_PLAN_CODES)).all()}
    paying_users = {
        r[0] for r in db.query(SubscriptionPayment.user_id).filter(
            SubscriptionPayment.status == "success", SubscriptionPayment.amount > 0
        ).distinct()
    }
    for sub in db.query(Subscription).all():
        user = db.get(User, sub.user_id)
        if (not sub.is_trial and sub.plan_id in trial_plan_ids and sub.end_date is not None
                and user is not None and user.has_used_trial and sub.user_id not in paying_users):
            sub.is_trial = True
            counts["trials"] += 1
        if not db.query(SubscriptionEvent.event_id).filter(SubscriptionEvent.subscription_id == sub.subscription_id).first():
            billing.record_event(db, sub, "migrated", to_plan_id=sub.plan_id,
                                 reason="Starting state when subscription history began", at=sub.start_date)
            counts["events"] += 1

    db.flush()
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        before = _totals(db)
        counts = backfill(db)
        after = _totals(db)

        print("Backfill", "APPLIED" if args.apply else "DRY RUN (nothing written)")
        print("  created:", ", ".join(f"{k}={v}" for k, v in counts.items()))
        print(f"  {'':22} {'before':>14} {'after':>14}")
        for key in before:
            print(f"  {key:22} {str(before[key]):>14} {str(after[key]):>14}")

        expected_cash = after["payments_received"] - after["payments_refunded"]
        balanced = after["ledger_cash_net"] == expected_cash
        print(f"  check: ledger cash {after['ledger_cash_net']} vs payments - refunds {expected_cash}:",
              "OK" if balanced else "MISMATCH")

        if args.apply and balanced:
            db.commit()
        else:
            db.rollback()
            if args.apply:
                print("Not applied: the ledger does not reconcile with payments. Investigate before retrying.")
                sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
