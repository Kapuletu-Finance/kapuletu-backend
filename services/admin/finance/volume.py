"""
Contribution volume and ledger integrity, platform-wide and read-only.

This is the treasurers' money (group contributions), not Kapuletu revenue. Finance sees how much flows through
the platform and whether the sealed records are intact; it never edits them.
"""
import datetime
from collections import defaultdict
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.group import Group
from models.transaction import Transaction
from models.users import User
from services.finance.ledger_service import LedgerService

from .common import audit, iso, user_name

ZERO = Decimal("0")
INTEGRITY_LIMIT = 20000  # records checked per run; narrow the dates for more


class VolumeService:
    def __init__(self, db: Session):
        self.db = db

    def _approved(self, start: datetime.datetime, end: datetime.datetime):
        return self.db.query(Transaction).filter(
            Transaction.status == "approved", Transaction.created_at >= start, Transaction.created_at < end
        )

    def summary(self, start: datetime.datetime, end: datetime.datetime) -> dict:
        totals = self.db.query(func.count(Transaction.transaction_id), func.coalesce(func.sum(Transaction.amount), 0),
                               func.count(func.distinct(Transaction.group_id)),
                               func.count(func.distinct(Transaction.owner_id))).filter(
            Transaction.status == "approved", Transaction.created_at >= start, Transaction.created_at < end
        ).one()
        count, amount, groups, treasurers = totals

        by_month = defaultdict(lambda: [0, ZERO])
        by_method = defaultdict(lambda: [0, ZERO])
        for created_at, method, value in self.db.query(Transaction.created_at, Transaction.payment_method,
                                                       Transaction.amount).filter(
            Transaction.status == "approved", Transaction.created_at >= start, Transaction.created_at < end
        ):
            m = by_month[created_at.strftime("%Y-%m")]
            m[0] += 1
            m[1] += Decimal(str(value or 0))
            k = by_method[method or "Unknown"]
            k[0] += 1
            k[1] += Decimal(str(value or 0))

        top = self.db.query(Group.group_id, Group.group_name, Group.owner_id,
                            func.count(Transaction.transaction_id), func.sum(Transaction.amount)).join(
            Transaction, Transaction.group_id == Group.group_id
        ).filter(
            Transaction.status == "approved", Transaction.created_at >= start, Transaction.created_at < end
        ).group_by(Group.group_id, Group.group_name, Group.owner_id).order_by(func.sum(Transaction.amount).desc()).limit(10).all()
        owners = {u.user_id: u for u in self.db.query(User).filter(User.user_id.in_([t[2] for t in top]))} if top else {}

        return {
            "period": {"from": start.isoformat(), "to": end.isoformat()},
            "totals": {
                "contributions": count, "amount": float(amount or 0), "active_groups": groups,
                "active_treasurers": treasurers,
                "average_contribution": round(float(amount or 0) / count, 2) if count else 0.0,
            },
            "by_month": [{"month": k, "contributions": v[0], "amount": float(v[1])} for k, v in sorted(by_month.items())],
            "by_method": [{"method": k, "contributions": v[0], "amount": float(v[1])}
                          for k, v in sorted(by_method.items(), key=lambda x: -x[1][1])],
            "top_groups": [{
                "group_id": str(gid), "group_name": name, "treasurer": user_name(owners.get(owner)),
                "treasurer_id": str(owner), "contributions": n, "amount": float(total or 0),
            } for gid, name, owner, n, total in top],
        }

    def integrity(self, start: datetime.datetime, end: datetime.datetime, actor_id=None) -> dict:
        """Re-computes the SHA-256 seal of every approved contribution in the period."""
        hasher = LedgerService(self.db)
        checked = unsealed = 0
        tampered = []
        txns = self._approved(start, end).order_by(Transaction.created_at).limit(INTEGRITY_LIMIT + 1).all()
        truncated = len(txns) > INTEGRITY_LIMIT
        for txn in txns[:INTEGRITY_LIMIT]:
            checked += 1
            if not txn.ledger_hash:
                unsealed += 1
                continue
            if hasher._recalculate_hash(txn) != txn.ledger_hash:
                tampered.append(txn)

        groups = {g.group_id: g.group_name for g in self.db.query(Group).filter(
            Group.group_id.in_([t.group_id for t in tampered]))} if tampered else {}
        audit(self.db, actor_id, "LEDGER_INTEGRITY_CHECK", "LEDGER", None, {
            "from": iso(start), "to": iso(end), "checked": checked, "tampered": len(tampered), "unsealed": unsealed,
        })
        self.db.commit()
        return {
            "period": {"from": start.isoformat(), "to": end.isoformat()},
            "checked": checked,
            "intact": checked - unsealed - len(tampered),
            "unsealed": unsealed,
            "truncated": truncated,
            "tampered": [{
                "transaction_id": str(t.transaction_id), "group_name": groups.get(t.group_id),
                "transaction_code": t.transaction_code, "amount": float(t.amount or 0), "created_at": iso(t.created_at),
            } for t in tampered],
        }
