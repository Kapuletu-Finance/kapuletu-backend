import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, select

from common.database import get_db
from common.auth_dependencies import get_verified_user
from common.utils import parse_uuid
from services.finance.checkout_schemas import (
    PlanOut, MySubscriptionOut, CheckoutIn, CheckoutOut,
    PaymentStatusOut, BillingHistoryOut, PricingConfigOut, QuoteIn, QuoteOut, InvoiceOut, InvoiceLineOut,
)
from models.billing import CreditNote, Invoice, InvoiceLine, ProviderEvent
from models.transaction import Transaction
from models.subscription import Plan, Subscription, SubscriptionPayment
from sqlalchemy.exc import IntegrityError
from models.group import Group
from models.campaign import Campaign
from models.users import User
from services.finance.providers.mpesa import MpesaProvider
from services.finance.providers.flutterwave import FlutterwaveProvider
from services.finance.fulfillment import FulfillmentService
from services.finance import billing
from services.finance.plans import get_free_plan, get_trial_plan

router = APIRouter()

@router.get("/available-plans", response_model=List[PlanOut], summary="List Subscription Tiers")
async def list_available_plans(db: Session = Depends(get_db)):
    plans = db.execute(
        select(Plan).where(Plan.is_public.is_(True), Plan.archived_at.is_(None)).order_by(Plan.price.asc())
    ).scalars().all()
    currency = billing.get_settings(db).currency
    out = []
    for p in plans:
        prices = billing.plan_prices_out(db, p)
        out.append(PlanOut(
            id=str(p.plan_id),
            code=p.code,
            name=p.name,
            price=prices["monthly_price"],
            monthly_price=prices["monthly_price"],
            annual_price=prices["annual_price"],
            currency=currency,
            limits={
                "max_groups": p.max_groups,
                "max_campaigns": p.max_campaigns,
                "max_transactions_per_month": p.max_transactions_per_month
            },
            allowed_features=p.allowed_features or {},
        ))
    db.commit()  # current_price() may have created a missing price row
    return out

@router.get("/pricing-config", response_model=PricingConfigOut, summary="Public Billing Rules")
async def get_pricing_config(db: Session = Depends(get_db)):
    s = billing.get_settings(db)
    db.commit()
    return PricingConfigOut(
        currency=s.currency,
        trial_days=s.trial_days,
        annual_months_charged=s.annual_months_charged,
        addon_monthly_price=float(billing.money(s.addon_monthly_price)),
        tax_rate_percent=float(s.tax_rate_percent or 0),
    )

def _plan_for_checkout(db: Session, plan_id: str) -> Plan:
    try:
        plan = db.execute(select(Plan).where(Plan.plan_id == parse_uuid(plan_id))).scalars().first()
    except ValueError:
        plan = None
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan

@router.post("/quote", response_model=QuoteOut, summary="Price a Checkout")
async def quote_checkout(payload: QuoteIn, db: Session = Depends(get_db)):
    plan = _plan_for_checkout(db, payload.plan_id)
    try:
        quote = billing.build_quote(db, plan, payload.billing_cycle, payload.has_addons)
    except billing.BillingError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    db.commit()
    return QuoteOut(**quote.as_dict())

@router.get("/my-subscription", response_model=MySubscriptionOut, summary="View Active Subscription & Usage")
async def get_my_subscription(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = parse_uuid(current_user.get("sub"))
    user = db.execute(select(User).where(User.user_id == user_id)).scalars().first()
    has_used_trial = bool(user.has_used_trial) if user and user.has_used_trial is not None else False

    sub = db.execute(select(Subscription).where(Subscription.user_id == user_id)).scalars().first()
    
    if not sub:
        # Should not happen if onboarding sets trial, but fallback to the free tier
        free_plan = get_free_plan(db)
        return MySubscriptionOut(
            active_plan=free_plan.name if free_plan else "Free",
            is_on_trial=False,
            has_used_trial=has_used_trial,
            days_remaining=0,
            expiry_date=None,
            usage={"groups": "0/1", "campaigns": "0/1"},
            allowed_features=free_plan.allowed_features if free_plan else {},
            plan_code=free_plan.code if free_plan else None,
        )
        
    plan = db.execute(select(Plan).where(Plan.plan_id == sub.plan_id)).scalars().first()
    
    # Calculate days remaining
    days_remaining = 0
    if sub.end_date:
        delta = sub.end_date - datetime.datetime.utcnow()
        days_remaining = max(0, delta.days)
        
    is_on_trial = bool(sub.is_trial) and sub.status == "active"
    
    # Usage calculation
    groups_count = db.execute(select(Group).where(Group.owner_id == parse_uuid(user_id))).scalars().all()
    groups_count = len(groups_count)
    campaigns_count = db.execute(select(Campaign).join(Group).where(Group.owner_id == parse_uuid(user_id))).scalars().all()
    campaigns_count = len(campaigns_count)
    month_start = datetime.datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    transactions_count = db.execute(
        select(func.count(Transaction.transaction_id)).where(
            Transaction.owner_id == user_id, Transaction.status == "approved", Transaction.created_at >= month_start
        )
    ).scalar() or 0
    
    return MySubscriptionOut(
        active_plan=plan.name,
        is_on_trial=is_on_trial,
        has_used_trial=has_used_trial,
        days_remaining=days_remaining,
        expiry_date=sub.end_date.isoformat() if sub.end_date else None,
        usage={
            "groups": f"{groups_count}/{plan.max_groups}",
            "campaigns": f"{campaigns_count}/{plan.max_campaigns}",
            "transactions": f"{transactions_count}/{plan.max_transactions_per_month}",
        },
        allowed_features=plan.allowed_features or {},
        plan_code=plan.code,
    )

@router.post("/checkout", response_model=CheckoutOut, summary="Initiate Subscription Payment")
async def initiate_checkout(
    payload: CheckoutIn,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    import logging
    user_id = current_user.get("sub")
    user_uuid = parse_uuid(user_id)
    plan = _plan_for_checkout(db, payload.plan_id)

    if payload.provider == "mpesa":
        provider = MpesaProvider()
    elif payload.provider in ["flutterwave", "stripe"]:
        provider = FlutterwaveProvider()
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")

    try:
        quote = billing.build_quote(db, plan, payload.billing_cycle, payload.has_addons)
    except billing.BillingError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    if quote.total <= 0:
        raise HTTPException(status_code=400, detail="This plan is free; no payment is needed")

    user = db.execute(select(User).where(User.user_id == user_uuid)).scalars().first()

    # The payment must hang off a subscription; older users may not have one yet.
    sub = db.execute(select(Subscription).where(Subscription.user_id == user_uuid)).scalars().first()
    if not sub:
        free_plan = get_free_plan(db)
        if not free_plan:
            raise HTTPException(status_code=500, detail="Free plan is not configured")
        sub = Subscription(user_id=user_uuid, plan_id=free_plan.plan_id, status="active", is_auto_renew=False)
        db.add(sub)
        db.flush()

    invoice = billing.create_invoice(db, user_uuid, sub.subscription_id, quote)

    metadata = {
        "user_id": user_id,
        "plan_id": str(plan.plan_id),
        "price_id": str(quote.price.price_id),
        "invoice_id": str(invoice.invoice_id),
        "invoice_number": invoice.number,
        "phone_number": payload.phone_number if payload.phone_number else (user.phone_number if user else ""),
        "email": payload.email if payload.email else (user.email if user else ""),
        "name": payload.name if payload.name else (user.first_name if user else ""),
        "billing_cycle": payload.billing_cycle,
        "has_addons": payload.has_addons,
    }

    try:
        result = provider.initiate_checkout(user_id, str(plan.plan_id), float(quote.total), metadata)
    except Exception as e:
        logging.error(f"Checkout Provider Error: {str(e)}")
        billing.void_invoice(invoice, "Payment provider could not start the checkout")
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))

    if result.get("status") != "initiated" or not result.get("correlation_id"):
        billing.void_invoice(invoice, "Payment provider did not accept the checkout")
        db.commit()
        raise HTTPException(status_code=400, detail="The payment provider did not accept the checkout")

    db.add(SubscriptionPayment(
        user_id=user_uuid,
        subscription_id=sub.subscription_id,
        invoice_id=invoice.invoice_id,
        amount=quote.total,
        currency=quote.currency,
        status="pending",
        payment_method=payload.provider,
        provider_reference=result.get("correlation_id"),
        payment_metadata=metadata,
    ))
    db.commit()

    return CheckoutOut(
        checkout_id=result.get("correlation_id", "unknown"),
        status="initiated",
        provider_response=result
    )

@router.get("/status/{checkout_id}", response_model=PaymentStatusOut, summary="Check Payment Status")
async def get_payment_status(
    checkout_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = current_user.get("sub")
    
    import uuid
    is_uuid = False
    try:
        uuid.UUID(str(checkout_id))
        is_uuid = True
    except ValueError:
        pass

    if is_uuid:
        payment = db.execute(
            select(SubscriptionPayment).where(
                SubscriptionPayment.user_id == parse_uuid(user_id),
                (SubscriptionPayment.provider_reference == checkout_id) | (SubscriptionPayment.payment_id == checkout_id)
            )
        ).scalars().first()
    else:
        payment = db.execute(
            select(SubscriptionPayment).where(
                SubscriptionPayment.user_id == parse_uuid(user_id),
                SubscriptionPayment.provider_reference == checkout_id
            )
        ).scalars().first()
    
    if not payment:
        return PaymentStatusOut(status="pending", confirmed_at=None, plan=None)
        
    # Active Polling for M-Pesa
    if payment.status in ["pending", "initiated"] and payment.payment_method == "mpesa":
        try:
            from services.finance.providers.mpesa import MpesaProvider
            from services.finance.fulfillment import FulfillmentService
            import logging
            logger = logging.getLogger(__name__)
            
            provider_svc = MpesaProvider()
            query_res = provider_svc.stk_push_query(payment.provider_reference)
            
            if query_res.get("success"):
                logger.info(f"Active Polling detected success for {checkout_id}. Fulfilling now.")
                # Daraja confirmed this exact STK push, whose amount we set, so the expected amount is what was paid.
                fulfillment = FulfillmentService(db)
                fulfillment.process_success(
                    correlation_id=payment.provider_reference,
                    provider_ref=query_res.get("provider_ref", ""),
                    amount=payment.amount,
                    currency=payment.currency,
                )
                
                # Refresh payment to reflect success status
                db.refresh(payment)
            elif query_res.get("status") == "failed":
                # Only fail if explicitly cancelled or confirmed failed, to avoid premature failure on pending/timeouts
                raw_status = query_res.get("raw_status", "")
                if "cancel" in raw_status.lower() or "failed" in raw_status.lower():
                    FulfillmentService(db).process_failure(payment.provider_reference, raw_status)
                    db.refresh(payment)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Active STK polling failed: {e}")
            
    # Get plan name
    sub = db.execute(select(Subscription).where(Subscription.subscription_id == payment.subscription_id)).scalars().first()
    plan_name = None
    if sub:
        plan = db.execute(select(Plan).where(Plan.plan_id == sub.plan_id)).scalars().first()
        if plan: plan_name = plan.name
        
    return PaymentStatusOut(
        status=payment.status,
        confirmed_at=payment.created_at.isoformat() if payment.created_at else None,
        plan=plan_name
    )

@router.get("/receipt/{payment_id}", summary="Download Receipt (PDF)")
async def download_receipt(
    payment_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = parse_uuid(current_user.get("sub"))
    payment = db.execute(select(SubscriptionPayment).where(SubscriptionPayment.payment_id == parse_uuid(payment_id), SubscriptionPayment.user_id == user_id)).scalars().first()
    
    if not payment or payment.status != "success":
        raise HTTPException(status_code=404, detail="Receipt not found")
        
    sub = db.execute(select(Subscription).where(Subscription.subscription_id == payment.subscription_id)).scalars().first()
    plan = db.execute(select(Plan).where(Plan.plan_id == sub.plan_id)).scalars().first()
    user = db.execute(select(User).where(User.user_id == user_id)).scalars().first()
    
    from services.finance.receipt_document import render_subscription_receipt
    pdf_bytes, filename = render_subscription_receipt(db, payment, plan, user)

    from fastapi.responses import Response
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@router.get("/billing-history", response_model=List[BillingHistoryOut], summary="View Billing History")
async def get_billing_history(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = current_user.get("sub")
    rows = db.execute(
        select(SubscriptionPayment, Invoice.number, Plan.name)
        .outerjoin(Invoice, SubscriptionPayment.invoice_id == Invoice.invoice_id)
        .outerjoin(Subscription, SubscriptionPayment.subscription_id == Subscription.subscription_id)
        .outerjoin(Plan, Subscription.plan_id == Plan.plan_id)
        .where(SubscriptionPayment.user_id == parse_uuid(user_id))
        .order_by(desc(SubscriptionPayment.created_at))
    ).all()

    return [
        BillingHistoryOut(
            payment_id=str(p.payment_id),
            amount=float(p.amount or 0),
            currency=p.currency,
            status=p.status,
            payment_method=p.payment_method,
            provider_reference=(p.payment_metadata or {}).get("receipt_number") or p.provider_reference,
            created_at=p.created_at,
            transaction_type=p.transaction_type or "payment",
            invoice_number=invoice_number,
            plan_name=plan_name,
        ) for p, invoice_number, plan_name in rows
    ]

@router.get("/invoices", response_model=List[InvoiceOut], summary="My Invoices")
async def list_my_invoices(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = parse_uuid(current_user.get("sub"))
    invoices = db.execute(
        select(Invoice).where(Invoice.user_id == user_id, Invoice.status.in_(("open", "paid")))
        .order_by(desc(Invoice.issued_at))
    ).scalars().all()
    lines = {}
    if invoices:
        for line in db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id.in_([i.invoice_id for i in invoices]))).scalars():
            lines.setdefault(line.invoice_id, []).append(line)
    return [
        InvoiceOut(
            invoice_id=str(i.invoice_id), number=i.number, status=i.status, currency=i.currency,
            subtotal=float(i.subtotal or 0), tax=float(i.tax or 0), total=float(i.total or 0),
            billing_cycle=i.billing_cycle, period_start=i.period_start, period_end=i.period_end,
            issued_at=i.issued_at, paid_at=i.paid_at,
            lines=[InvoiceLineOut(description=l.description, quantity=l.quantity, amount=float(l.amount))
                   for l in lines.get(i.invoice_id, [])],
        ) for i in invoices
    ]

@router.get("/invoices/{invoice_id}/pdf", summary="Download Invoice (PDF)")
async def download_invoice(
    invoice_id: str,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = parse_uuid(current_user.get("sub"))
    try:
        invoice = db.execute(
            select(Invoice).where(Invoice.invoice_id == parse_uuid(invoice_id), Invoice.user_id == user_id)
        ).scalars().first()
    except ValueError:
        invoice = None
    if not invoice or invoice.status == "void":
        raise HTTPException(status_code=404, detail="Invoice not found")
    lines = db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.invoice_id)).scalars().all()
    credit_notes = db.execute(select(CreditNote).where(CreditNote.invoice_id == invoice.invoice_id)).scalars().all()
    user = db.execute(select(User).where(User.user_id == user_id)).scalars().first()

    from services.finance.receipt_document import render_invoice
    pdf_bytes, filename = render_invoice(db, invoice, lines, user, credit_notes)
    from fastapi.responses import Response
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@router.post("/cancel-subscription", summary="Cancel Auto-Renew (no effect: plans don't auto-renew yet)")
async def cancel_subscription(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = current_user.get("sub")
    sub = db.execute(select(Subscription).where(Subscription.user_id == parse_uuid(user_id))).scalars().first()
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription found")
        
    sub.is_auto_renew = False
    billing.record_event(db, sub, "cancel_requested", from_plan_id=sub.plan_id, actor_id=sub.user_id)
    db.commit()
    return {"status": "success", "message": "Auto-renewal cancelled. Your subscription will downgrade upon expiration."}

@router.post("/webhook/flutterwave", summary="Flutterwave Webhook (legacy path)")
async def flutterwave_webhook(request: Request, db: Session = Depends(get_db)):
    # Older dashboards were configured with this path; handle it exactly like /webhooks/flutterwave.
    return await webhook_callback("flutterwave", request, db)

@router.post("/activate-trial", summary="Activate Professional Trial")
async def activate_trial(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = parse_uuid(current_user.get("sub"))
    user = db.execute(select(User).where(User.user_id == user_id)).scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if getattr(user, 'has_used_trial', False):
        raise HTTPException(status_code=400, detail="You have already consumed your free trial.")
        
    pro_plan = get_trial_plan(db)
    if not pro_plan:
        raise HTTPException(status_code=500, detail="Professional plan not found in system")

    trial_days = billing.get_settings(db).trial_days
    now = datetime.datetime.utcnow()
    sub = db.execute(select(Subscription).where(Subscription.user_id == user_id)).scalars().first()
    from_plan_id = sub.plan_id if sub else None

    if not sub:
        sub = Subscription(
            user_id=user_id,
            plan_id=pro_plan.plan_id,
            status="active",
            start_date=now,
            end_date=now + datetime.timedelta(days=trial_days),
            is_auto_renew=False
        )
        db.add(sub)
    else:
        sub.plan_id = pro_plan.plan_id
        sub.status = "active"
        sub.start_date = now
        sub.end_date = now + datetime.timedelta(days=trial_days)
        sub.is_auto_renew = False
    sub.is_trial = True
    sub.price_id = None
    db.flush()
    billing.record_event(db, sub, "trial_started", from_plan_id=from_plan_id, to_plan_id=pro_plan.plan_id,
                         actor_id=user_id, at=now)

    user.has_used_trial = True
    db.commit()
    
    # Send Trial Activation Email
    if user.email:
        try:
            from services.communications.outbox import queue_email
            from services.notifications.templates.render import render_email_template
            
            subject = f"Welcome to KapuLetu {pro_plan.name}!"
            html_body = render_email_template(
                "trial_started.html",
                name=user.first_name or "User",
                plan_name=pro_plan.name,
                expiry_date=sub.end_date.strftime('%B %d, %Y')
            )
            
            queue_email(db, user.email, subject, html_body, kind="trial_started", user_id=user.user_id, layout=False)
            db.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to queue trial activation email: {e}")
    
    return {"message": "Trial activated successfully", "plan": pro_plan.name}

@router.post("/webhooks/{provider}", summary="Payment Webhook")
async def webhook_callback(provider: str, request: Request, db: Session = Depends(get_db)):
    import logging
    logger = logging.getLogger(__name__)
    
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    logger.info(f"WEBHOOK RECEIVED [{provider}]: {body_str}")
    
    import json
    payload = json.loads(body_str) if body_str else {}
    
    if provider == "mpesa":
        provider_svc = MpesaProvider()
    elif provider in ["flutterwave", "stripe"]:
        provider_svc = FlutterwaveProvider()
    else:
        raise HTTPException(status_code=400, detail="Unknown provider")
        
    if not provider_svc.verify_webhook(body_str, dict(request.headers), dict(request.query_params)):
        logger.error(f"WEBHOOK SIGNATURE INVALID for {provider}")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        event_data = provider_svc.parse_webhook_payload(payload)
        logger.info(f"WEBHOOK PARSED EVENT DATA: {event_data}")
    except Exception as e:
        logger.error(f"WEBHOOK PARSE FAILED: {str(e)}")
        _store_provider_event(db, provider, None, None, payload, body_str, outcome="parse_failed")
        return {"received": True, "error": "parse_failed"}

    correlation_id = event_data.get("correlation_id") or ""
    event = _store_provider_event(db, provider, correlation_id, event_data, payload, body_str)
    if event is None:
        logger.info(f"WEBHOOK REPLAY ignored for {provider} {correlation_id}")
        return {"received": True, "duplicate": True}

    fulfillment = FulfillmentService(db)

    def finish(outcome: str):
        event.outcome = outcome
        event.processed_at = datetime.datetime.utcnow()
        db.add(event)
        db.commit()

    if not event_data.get("success"):
        logger.warning(f"WEBHOOK REPORTED FAILURE for {correlation_id}: {event_data.get('raw_status')}")
        failed = bool(correlation_id) and fulfillment.process_failure(correlation_id, str(event_data.get("raw_status") or ""))
        finish("failed" if failed else "ignored")
        return {"received": True}

    # M-Pesa callbacks are unsigned: only trust a success that Daraja itself confirms for this checkout.
    if provider == "mpesa":
        confirmation = provider_svc.stk_push_query(correlation_id)
        if not confirmation.get("success"):
            logger.error(f"WEBHOOK SUCCESS NOT CONFIRMED by STK query for {correlation_id}: {confirmation}")
            finish("unconfirmed")
            return {"received": True, "error": "unconfirmed"}

    try:
        fulfillment_result = fulfillment.process_success(
            correlation_id=correlation_id,
            provider_ref=event_data.get("provider_ref", ""),
            amount=event_data.get("amount", 0),
            currency=event_data.get("currency"),
        )
        logger.info(f"WEBHOOK FULFILLMENT RESULT: {fulfillment_result}")
        finish("fulfilled" if fulfillment_result else "refused")
    except Exception as e:
        db.rollback()
        logger.exception(f"WEBHOOK FULFILLMENT CRASHED: {str(e)}")
        finish("error")
        return {"received": True, "error": "fulfillment_crashed"}

    return {"received": True}


# Outcomes after which a repeat of the same callback is ignored. Others (unconfirmed, error) may be retried.
FINAL_EVENT_OUTCOMES = ("fulfilled", "failed", "refused", "ignored", "parse_failed")


def _store_provider_event(db: Session, provider: str, correlation_id, event_data, payload, body_str: str,
                          outcome: str = None):
    """
    Saves the raw callback before anything acts on it. Returns the event row to process,
    or None when the same callback was already handled to a final outcome.
    """
    import hashlib
    status = (event_data or {}).get("raw_status") or ("success" if (event_data or {}).get("success") else "failure")
    key = f"{correlation_id}:{status}" if correlation_id else "sha256:" + hashlib.sha256(body_str.encode()).hexdigest()
    existing = db.execute(
        select(ProviderEvent).where(ProviderEvent.provider == provider, ProviderEvent.event_key == key)
    ).scalars().first()
    if existing:
        if existing.outcome in FINAL_EVENT_OUTCOMES:
            return None
        existing.payload = payload if isinstance(payload, dict) else {"raw": body_str}
        db.commit()
        return existing
    event = ProviderEvent(
        provider=provider, event_key=key, correlation_id=correlation_id or None,
        payload=payload if isinstance(payload, dict) else {"raw": body_str}, verified=True, outcome=outcome,
        processed_at=datetime.datetime.utcnow() if outcome else None,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        # The same callback arrived twice at once; the other request is handling it.
        db.rollback()
        return None
    return event
