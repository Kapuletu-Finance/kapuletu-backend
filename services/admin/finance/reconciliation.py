"""
Reconciliation: does the money the providers say we received agree with the payments we recorded?

- M-Pesa: Daraja has no statement API, so finance uploads the CSV statement from the M-Pesa org portal.
- Flutterwave: pulled from its transactions API (on demand, and daily by the finance scheduler).

Each provider line is matched to a payment by M-Pesa receipt or Flutterwave checkout reference. M-Pesa payments
confirmed by status polling never received a receipt, so those fall back to same amount within 15 minutes.
Whatever doesn't agree becomes an item in the mismatch queue for finance to resolve.
"""
import csv
import datetime
import io
import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

import requests
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.finance_ops import ReconciliationItem, ReconciliationRun
from models.subscription import SubscriptionPayment
from models.users import User

from .common import FinanceError, as_uuid, audit, iso, page_params, paged, user_name

logger = logging.getLogger(__name__)

EAT_OFFSET = datetime.timedelta(hours=3)  # statements are in Nairobi time; we store UTC
TIME_TOLERANCE = datetime.timedelta(minutes=15)
PROVIDER_METHODS = {"mpesa": ("mpesa",), "flutterwave": ("flutterwave", "stripe")}
ITEM_STATUSES = ("matched", "amount_mismatch", "missing_in_ledger", "missing_in_statement")


def _money(value) -> Optional[Decimal]:
    if value is None:
        return None
    text = str(value).replace(",", "").replace("KES", "").strip()
    if not text:
        return None
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _parse_time(text: str) -> Optional[datetime.datetime]:
    text = (text or "").strip()
    for fmt in ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M"):
        try:
            return datetime.datetime.strptime(text, fmt) - EAT_OFFSET
        except ValueError:
            continue
    return None


def parse_mpesa_statement(content: bytes) -> List[dict]:
    """
    Reads an M-Pesa org-portal statement export. Finds the header row (the one naming "Receipt No."),
    keeps completed lines with money paid in, and returns them as provider lines.
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    rows = list(csv.reader(io.StringIO(text)))
    header_at = next((i for i, row in enumerate(rows) if any("receipt no" in c.lower() for c in row)), None)
    if header_at is None:
        raise FinanceError("This doesn't look like an M-Pesa statement: no 'Receipt No.' column found")

    header = [c.strip().lower().rstrip(".") for c in rows[header_at]]

    def col(*names):
        for name in names:
            for i, h in enumerate(header):
                if h.startswith(name):
                    return i
        return None

    receipt_i, time_i = col("receipt no"), col("completion time", "initiation time")
    status_i, paid_i = col("transaction status"), col("paid in")
    party_i, details_i = col("other party info", "other party"), col("details")
    if receipt_i is None or time_i is None or paid_i is None:
        raise FinanceError("The statement needs 'Receipt No.', 'Completion Time' and 'Paid In' columns")

    lines = []
    for row in rows[header_at + 1:]:
        if len(row) <= max(receipt_i, time_i, paid_i):
            continue
        receipt = row[receipt_i].strip()
        amount = _money(row[paid_i])
        if not receipt or not amount or amount <= 0:
            continue
        if status_i is not None and status_i < len(row) and row[status_i].strip().lower() not in ("completed", ""):
            continue
        lines.append({
            "ref": receipt,
            "key": receipt,
            "amount": amount,
            "at": _parse_time(row[time_i]),
            "counterparty": row[party_i].strip() if party_i is not None and party_i < len(row) else None,
            "raw": {header[i]: row[i] for i in range(min(len(header), len(row))) if header[i]},
        })
    if details_i is None:
        logger.info("M-Pesa statement has no Details column; continuing without it")
    return lines


def fetch_flutterwave_transactions(start: datetime.date, end: datetime.date) -> List[dict]:
    """Successful Flutterwave transactions between two dates (inclusive), as provider lines."""
    secret = os.environ.get("FLW_SECRET_KEY")
    if not secret:
        raise FinanceError("Flutterwave isn't configured (FLW_SECRET_KEY is not set)", 400)
    lines, page = [], 1
    while True:
        res = requests.get(
            "https://api.flutterwave.com/v3/transactions",
            params={"from": start.isoformat(), "to": end.isoformat(), "status": "successful", "page": page},
            headers={"Authorization": f"Bearer {secret}"},
            timeout=20,
        )
        if res.status_code != 200:
            raise FinanceError(f"Flutterwave returned {res.status_code}: {res.text[:200]}", 502)
        body = res.json()
        for tx in body.get("data") or []:
            created = tx.get("created_at")
            at = datetime.datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None) if created else None
            customer = tx.get("customer") or {}
            lines.append({
                "ref": str(tx.get("id")),
                "key": tx.get("tx_ref") or str(tx.get("id")),  # our checkout reference
                "amount": _money(tx.get("amount")),
                "currency": tx.get("currency"),
                "at": at,
                "counterparty": customer.get("email") or customer.get("phone_number"),
                "raw": {k: tx.get(k) for k in ("id", "tx_ref", "flw_ref", "amount", "currency", "status", "created_at",
                                               "payment_type")},
            })
        info = (body.get("meta") or {}).get("page_info") or {}
        if page >= int(info.get("total_pages") or 1):
            return lines
        page += 1


class ReconciliationService:
    def __init__(self, db: Session):
        self.db = db

    # --- running ---

    def _candidates(self, provider: str, start: datetime.datetime, end: datetime.datetime) -> List[SubscriptionPayment]:
        return self.db.query(SubscriptionPayment).filter(
            SubscriptionPayment.payment_method.in_(PROVIDER_METHODS[provider]),
            SubscriptionPayment.status == "success",
            or_(SubscriptionPayment.transaction_type.is_(None), SubscriptionPayment.transaction_type == "payment"),
            SubscriptionPayment.created_at >= start - datetime.timedelta(days=1),
            SubscriptionPayment.created_at < end + datetime.timedelta(days=1),
        ).all()

    def _upsert(self, run: ReconciliationRun, provider: str, ref_key: str, **fields) -> ReconciliationItem:
        item = self.db.query(ReconciliationItem).filter(
            ReconciliationItem.provider == provider, ReconciliationItem.ref_key == ref_key
        ).first()
        if item is None:
            item = ReconciliationItem(provider=provider, ref_key=ref_key)
            self.db.add(item)
        item.run_id = run.run_id
        item.updated_at = datetime.datetime.utcnow()
        for key, value in fields.items():
            setattr(item, key, value)
        return item

    def reconcile(self, provider: str, lines: List[dict], source: str, source_name: Optional[str] = None,
                  period: Optional[tuple] = None, actor_id=None) -> dict:
        if provider not in PROVIDER_METHODS:
            raise FinanceError("provider must be mpesa or flutterwave")
        times = [line["at"] for line in lines if line.get("at")]
        if period:
            start, end = period
        elif times:
            start, end = min(times), max(times) + datetime.timedelta(seconds=1)
        else:
            raise FinanceError("The statement has no paid-in lines to reconcile")

        run = ReconciliationRun(provider=provider, source=source, source_name=source_name, period_start=start,
                                period_end=end, lines=len(lines), created_by=as_uuid(actor_id))
        self.db.add(run)
        self.db.flush()

        payments = self._candidates(provider, start, end)
        if provider == "mpesa":
            by_key = {(p.payment_metadata or {}).get("receipt_number"): p for p in payments
                      if (p.payment_metadata or {}).get("receipt_number")}
        else:
            by_key = {p.provider_reference: p for p in payments if p.provider_reference}

        used: set = set()
        unmatched_lines = []
        for line in lines:
            payment = by_key.get(line["key"])
            if payment is None or payment.payment_id in used:
                unmatched_lines.append(line)
                continue
            used.add(payment.payment_id)
            self._record_match(run, provider, line, payment, "receipt" if provider == "mpesa" else "reference")

        # M-Pesa payments confirmed by polling have no receipt: same amount within 15 minutes, nearest first.
        if provider == "mpesa":
            remaining = []
            for line in unmatched_lines:
                pool = [p for p in payments if p.payment_id not in used
                        and not (p.payment_metadata or {}).get("receipt_number")
                        and Decimal(str(p.amount)) == line["amount"] and line.get("at")
                        and abs(p.created_at - line["at"]) <= TIME_TOLERANCE]
                if not pool:
                    remaining.append(line)
                    continue
                payment = min(pool, key=lambda p: abs(p.created_at - line["at"]))
                used.add(payment.payment_id)
                meta = dict(payment.payment_metadata or {})
                meta["receipt_number"] = line["ref"]
                meta["receipt_source"] = "statement"
                payment.payment_metadata = meta
                self._record_match(run, provider, line, payment, "amount_time")
            unmatched_lines = remaining

        for line in unmatched_lines:
            self._upsert(run, provider, line["key"], provider_ref=line["ref"], provider_amount=line["amount"],
                         provider_at=line.get("at"), counterparty=line.get("counterparty"), raw=line.get("raw"),
                         payment_id=None, ledger_amount=None, status="missing_in_ledger", match_method=None)

        for payment in payments:
            if payment.payment_id in used or not (start <= payment.created_at < end):
                continue
            self._upsert(run, provider, f"payment:{payment.payment_id}",
                         provider_ref=(payment.payment_metadata or {}).get("receipt_number") or payment.provider_reference,
                         payment_id=payment.payment_id, ledger_amount=payment.amount, provider_amount=None,
                         provider_at=None, status="missing_in_statement", match_method=None)

        self.db.flush()
        statuses = [i.status for i in self.db.query(ReconciliationItem).filter(ReconciliationItem.run_id == run.run_id)]
        run.matched = statuses.count("matched")
        run.mismatched = len(statuses) - run.matched
        audit(self.db, actor_id, "RECONCILIATION_RUN", "RECONCILIATION", run.run_id, {
            "provider": provider, "source": source, "file": source_name, "lines": run.lines,
            "matched": run.matched, "mismatched": run.mismatched,
        })
        self.db.commit()
        return self._run_out(run)

    def _record_match(self, run, provider, line, payment, method):
        ours = Decimal(str(payment.amount)).quantize(Decimal("0.01"))
        currency_ok = not line.get("currency") or line["currency"].upper() == (payment.currency or "KES").upper()
        status = "matched" if line["amount"] == ours and currency_ok else "amount_mismatch"
        self._upsert(run, provider, line["key"], provider_ref=line["ref"], provider_amount=line["amount"],
                     provider_at=line.get("at"), counterparty=line.get("counterparty"), raw=line.get("raw"),
                     payment_id=payment.payment_id, ledger_amount=ours, status=status, match_method=method)
        # A payment flagged as missing in an earlier run is now accounted for.
        earlier = self.db.query(ReconciliationItem).filter(
            ReconciliationItem.provider == provider, ReconciliationItem.ref_key == f"payment:{payment.payment_id}"
        ).first()
        if earlier and earlier.status == "missing_in_statement":
            earlier.status, earlier.match_method, earlier.run_id = "matched", method, run.run_id
            earlier.provider_ref, earlier.updated_at = line["ref"], datetime.datetime.utcnow()

    def import_mpesa(self, content: bytes, filename: str, actor_id) -> dict:
        return self.reconcile("mpesa", parse_mpesa_statement(content), "upload", filename, actor_id=actor_id)

    def pull_flutterwave(self, start: datetime.date, end: datetime.date, actor_id=None) -> dict:
        lines = fetch_flutterwave_transactions(start, end)
        period = (datetime.datetime.combine(start, datetime.time()),
                  datetime.datetime.combine(end + datetime.timedelta(days=1), datetime.time()))
        return self.reconcile("flutterwave", lines, "api", f"{start} to {end}", period=period, actor_id=actor_id)

    # --- queue ---

    @staticmethod
    def _run_out(run: ReconciliationRun) -> dict:
        return {
            "run_id": str(run.run_id), "provider": run.provider, "source": run.source, "source_name": run.source_name,
            "period_start": iso(run.period_start), "period_end": iso(run.period_end), "lines": run.lines,
            "matched": run.matched, "mismatched": run.mismatched, "created_at": iso(run.created_at),
        }

    def list_runs(self, page: int = 1, limit: int = 20) -> dict:
        query = self.db.query(ReconciliationRun)
        total = query.count()
        offset, limit = page_params(page, limit)
        runs = query.order_by(ReconciliationRun.created_at.desc()).offset(offset).limit(limit).all()
        return paged([self._run_out(r) for r in runs], total, page, limit)

    def list_items(self, status: Optional[str] = None, provider: Optional[str] = None, open_only: bool = True,
                   run_id: Optional[str] = None, page: int = 1, limit: int = 50) -> dict:
        query = self.db.query(ReconciliationItem)
        if status:
            if status not in ITEM_STATUSES:
                raise FinanceError(f"status must be one of {', '.join(ITEM_STATUSES)}")
            query = query.filter(ReconciliationItem.status == status)
        elif open_only:
            query = query.filter(ReconciliationItem.status != "matched")
        if open_only:
            query = query.filter(ReconciliationItem.resolution.is_(None))
        if provider:
            query = query.filter(ReconciliationItem.provider == provider)
        if run_id:
            query = query.filter(ReconciliationItem.run_id == as_uuid(run_id))
        total = query.count()
        offset, limit = page_params(page, limit)
        items = query.order_by(ReconciliationItem.provider_at.desc().nullslast(), ReconciliationItem.updated_at.desc()
                               ).offset(offset).limit(limit).all()

        payments = {p.payment_id: p for p in self.db.query(SubscriptionPayment).filter(
            SubscriptionPayment.payment_id.in_([i.payment_id for i in items if i.payment_id]))} if items else {}
        users = {u.user_id: u for u in self.db.query(User).filter(
            User.user_id.in_([p.user_id for p in payments.values()]))} if payments else {}

        def out(i: ReconciliationItem) -> dict:
            p = payments.get(i.payment_id)
            return {
                "item_id": str(i.item_id), "provider": i.provider, "status": i.status, "match_method": i.match_method,
                "provider_ref": i.provider_ref, "provider_amount": float(i.provider_amount) if i.provider_amount is not None else None,
                "provider_at": iso(i.provider_at), "counterparty": i.counterparty,
                "payment_id": str(i.payment_id) if i.payment_id else None,
                "ledger_amount": float(i.ledger_amount) if i.ledger_amount is not None else None,
                "payment_at": iso(p.created_at) if p else None,
                "user_id": str(p.user_id) if p else None,
                "user_name": user_name(users.get(p.user_id)) if p else None,
                "resolution": i.resolution, "resolution_note": i.resolution_note, "resolved_at": iso(i.resolved_at),
                "raw": i.raw,
            }
        return paged([out(i) for i in items], total, page, limit)

    def open_counts(self) -> Dict[str, int]:
        counts = {s: 0 for s in ITEM_STATUSES if s != "matched"}
        for (status,) in self.db.query(ReconciliationItem.status).filter(
            ReconciliationItem.status != "matched", ReconciliationItem.resolution.is_(None)
        ):
            counts[status] += 1
        return counts

    def resolve(self, item_id: str, resolution: str, note: str, actor_id) -> dict:
        if resolution not in ("resolved", "ignored"):
            raise FinanceError("resolution must be resolved or ignored")
        try:
            item = self.db.get(ReconciliationItem, as_uuid(item_id))
        except ValueError:
            item = None
        if not item:
            raise FinanceError("Reconciliation item not found", 404)
        if item.status == "matched":
            raise FinanceError("Matched items need no resolution")
        item.resolution, item.resolution_note = resolution, note
        item.resolved_by, item.resolved_at = as_uuid(actor_id), datetime.datetime.utcnow()
        audit(self.db, actor_id, "RECONCILIATION_ITEM_RESOLVED", "RECONCILIATION_ITEM", item.item_id, {
            "status": item.status, "provider": item.provider, "provider_ref": item.provider_ref,
            "resolution": resolution, "note": note,
        })
        self.db.commit()
        return {"item_id": str(item.item_id), "resolution": resolution}
