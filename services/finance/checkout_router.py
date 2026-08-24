import datetime
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from common.database import get_db
from common.auth_dependencies import get_verified_user
from common.utils import parse_uuid
from services.finance.checkout_schemas import (
    PlanOut, MySubscriptionOut, CheckoutIn, CheckoutOut, 
    PaymentStatusOut, BillingHistoryOut
)
from models.subscription import Plan, Subscription, SubscriptionPayment
from models.group import Group
from models.campaign import Campaign
from services.finance.providers.mpesa import MpesaProvider
from services.finance.providers.flutterwave import FlutterwaveProvider
from services.finance.fulfillment import FulfillmentService

router = APIRouter()

@router.get("/available-plans", response_model=List[PlanOut], summary="List Subscription Tiers")
async def list_available_plans(db: Session = Depends(get_db)):
    plans = db.execute(select(Plan)).scalars().all()
    return [
        PlanOut(
            id=str(p.plan_id),
            name=p.name,
            price=float(p.price),
            limits={
                "max_groups": p.max_groups,
                "max_campaigns": p.max_campaigns,
                "max_transactions_per_month": p.max_transactions_per_month
            }
        ) for p in plans
    ]

@router.get("/my-subscription", response_model=MySubscriptionOut, summary="View Active Subscription & Usage")
async def get_my_subscription(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = parse_uuid(current_user.get("sub"))
    sub = db.execute(select(Subscription).where(Subscription.user_id == parse_uuid(user_id))).scalars().first()
    
    if not sub:
        # Should not happen if onboarding sets trial, but fallback to Free
        free_plan = db.execute(select(Plan).where(Plan.name == "Free")).scalars().first()
        return MySubscriptionOut(
            active_plan=free_plan.name if free_plan else "Free",
            is_on_trial=False,
            days_remaining=0,
            expiry_date=None,
            usage={"groups": "0/1", "campaigns": "0/1"}
        )
        
    plan = db.execute(select(Plan).where(Plan.plan_id == sub.plan_id)).scalars().first()
    
    # Calculate days remaining
    days_remaining = 0
    if sub.end_date:
        delta = sub.end_date - datetime.datetime.utcnow()
        days_remaining = max(0, delta.days)
        
    is_on_trial = (plan.name == "Professional" and sub.status == "active" and not db.execute(select(SubscriptionPayment).where(SubscriptionPayment.user_id == parse_uuid(user_id), SubscriptionPayment.status == "success")).first())
    
    # Usage calculation
    groups_count = db.execute(select(Group).where(Group.owner_id == parse_uuid(user_id))).scalars().all()
    groups_count = len(groups_count)
    campaigns_count = db.execute(select(Campaign).join(Group).where(Group.owner_id == parse_uuid(user_id))).scalars().all()
    campaigns_count = len(campaigns_count)
    
    return MySubscriptionOut(
        active_plan=plan.name,
        is_on_trial=is_on_trial,
        days_remaining=days_remaining,
        expiry_date=sub.end_date.isoformat() if sub.end_date else None,
        usage={
            "groups": f"{groups_count}/{plan.max_groups}",
            "campaigns": f"{campaigns_count}/{plan.max_campaigns}"
        }
    )

@router.post("/checkout", response_model=CheckoutOut, summary="Initiate Subscription Payment")
async def initiate_checkout(
    payload: CheckoutIn,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = current_user.get("sub")
    plan = db.execute(select(Plan).where(Plan.plan_id == payload.plan_id)).scalars().first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
        
    metadata = {
        "user_id": user_id,
        "plan_id": str(plan.plan_id),
        "phone_number": payload.phone_number,
        "email": payload.email,
        "name": payload.name
    }
    
    if payload.provider == "mpesa":
        provider = MpesaProvider()
    elif payload.provider in ["flutterwave", "stripe"]:
        provider = FlutterwaveProvider()
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")
        
    result = provider.initiate_checkout(user_id, str(plan.plan_id), plan.price, metadata)
    
    # Save the pending checkout attempt
    if result.get("status") == "initiated":
        # We need the user's current subscription to link the payment
        sub = db.execute(select(Subscription).where(Subscription.user_id == parse_uuid(user_id))).scalars().first()
        if not sub:
            # Fallback for old users: create a Free plan subscription so they can upgrade
            free_plan = db.execute(select(Plan).where(Plan.name == "Free")).scalars().first()
            if free_plan:
                sub = Subscription(
                    user_id=parse_uuid(user_id),
                    plan_id=free_plan.plan_id,
                    status="active",
                    is_auto_renew=False
                )
                db.add(sub)
                db.commit()
                db.refresh(sub)
                
        if sub:
            pending_payment = SubscriptionPayment(
                user_id=parse_uuid(user_id),
                subscription_id=sub.subscription_id,
                amount=plan.price,
                currency="KES",
                status="pending",
                payment_method=payload.provider,
                provider_reference=result.get("correlation_id"),
                payment_metadata={"plan_id": str(plan.plan_id)}
            )
            db.add(pending_payment)
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
    payment = db.execute(
        select(SubscriptionPayment).where(
            SubscriptionPayment.user_id == parse_uuid(user_id),
            (SubscriptionPayment.provider_reference == checkout_id) | (SubscriptionPayment.payment_id == checkout_id)
        )
    ).scalars().first()
    
    if not payment:
        return PaymentStatusOut(status="pending", confirmed_at=None, plan=None)
        
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

@router.get("/billing-history", response_model=List[BillingHistoryOut], summary="View Billing History")
async def get_billing_history(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = current_user.get("sub")
    payments = db.execute(
        select(SubscriptionPayment)
        .where(SubscriptionPayment.user_id == parse_uuid(user_id))
        .order_by(desc(SubscriptionPayment.created_at))
    ).scalars().all()
    
    return [
        BillingHistoryOut(
            payment_id=str(p.payment_id),
            amount=p.amount,
            currency=p.currency,
            status=p.status,
            payment_method=p.payment_method,
            provider_reference=p.provider_reference,
            created_at=p.created_at
        ) for p in payments
    ]

@router.post("/cancel-subscription", summary="Cancel Auto-Renew")
async def cancel_subscription(
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_verified_user)
):
    user_id = current_user.get("sub")
    sub = db.execute(select(Subscription).where(Subscription.user_id == parse_uuid(user_id))).scalars().first()
    if not sub:
        raise HTTPException(status_code=404, detail="No active subscription found")
        
    sub.is_auto_renew = False
    db.commit()
    return {"status": "success", "message": "Auto-renewal cancelled. Your subscription will downgrade upon expiration."}

@router.post("/webhooks/{provider}", summary="Payment Webhook")
async def webhook_callback(provider: str, request: Request, db: Session = Depends(get_db)):
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")
    import json
    payload = json.loads(body_str) if body_str else {}
    
    if provider == "mpesa":
        provider_svc = MpesaProvider()
    elif provider in ["flutterwave", "stripe"]:
        provider_svc = FlutterwaveProvider()
    else:
        raise HTTPException(status_code=400, detail="Unknown provider")
        
    if not provider_svc.verify_webhook(body_str, dict(request.headers)):
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    event_data = provider_svc.parse_webhook_payload(payload)
    if event_data.get("success"):
        fulfillment = FulfillmentService(db)
        
        # Look up pending payment by correlation_id (CheckoutRequestID)
        correlation_id = event_data.get("correlation_id", "")
        pending_payment = db.execute(
            select(SubscriptionPayment).where(SubscriptionPayment.provider_reference == correlation_id)
        ).scalars().first()
        
        metadata = {}
        if pending_payment:
            metadata = {
                "user_id": str(pending_payment.user_id),
                "plan_id": pending_payment.payment_metadata.get("plan_id") if pending_payment.payment_metadata else None
            }
            
        fulfillment.process_success(
            correlation_id=correlation_id,
            provider_ref=event_data.get("provider_ref", ""),
            amount=event_data.get("amount", 0.0),
            metadata=metadata
        )
        
    return {"received": True}
