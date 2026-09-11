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
from models.users import User
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
    user = db.execute(select(User).where(User.user_id == user_id)).scalars().first()
    has_used_trial = bool(user.has_used_trial) if user and user.has_used_trial is not None else False

    sub = db.execute(select(Subscription).where(Subscription.user_id == user_id)).scalars().first()
    
    if not sub:
        # Should not happen if onboarding sets trial, but fallback to Free
        free_plan = db.execute(select(Plan).where(Plan.name == "Free")).scalars().first()
        return MySubscriptionOut(
            active_plan=free_plan.name if free_plan else "Free",
            is_on_trial=False,
            has_used_trial=has_used_trial,
            days_remaining=0,
            expiry_date=None,
            usage={"groups": "0/1", "campaigns": "0/1"},
            allowed_features=free_plan.allowed_features if free_plan else {}
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
        has_used_trial=has_used_trial,
        days_remaining=days_remaining,
        expiry_date=sub.end_date.isoformat() if sub.end_date else None,
        usage={
            "groups": f"{groups_count}/{plan.max_groups}",
            "campaigns": f"{campaigns_count}/{plan.max_campaigns}"
        },
        allowed_features=plan.allowed_features or {}
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
        
    user = db.execute(select(User).where(User.user_id == parse_uuid(user_id))).scalars().first()
        
    metadata = {
        "user_id": user_id,
        "plan_id": str(plan.plan_id),
        "phone_number": payload.phone_number if payload.phone_number else (user.phone_number if user else ""),
        "email": payload.email if payload.email else (user.email if user else ""),
        "name": payload.name if payload.name else (user.first_name if user else ""),
        "billing_cycle": payload.billing_cycle
    }
    
    amount = float(plan.price)
    if payload.billing_cycle == "annual":
        amount = amount * 11
    if payload.has_addons:
        amount += 200.0
    
    if payload.provider == "mpesa":
        provider = MpesaProvider()
    elif payload.provider in ["flutterwave", "stripe"]:
        provider = FlutterwaveProvider()
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")
        
    try:
        result = provider.initiate_checkout(user_id, str(plan.plan_id), amount, metadata)
    except ValueError as e:
        import logging
        logging.error(f"Checkout Provider Error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    
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
                amount=amount,
                currency="KES",
                status="pending",
                payment_method=payload.provider,
                provider_reference=result.get("correlation_id"),
                payment_metadata=metadata
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
                fulfillment = FulfillmentService(db)
                meta_payload = payment.payment_metadata if payment.payment_metadata else {}
                meta_payload["user_id"] = str(payment.user_id)
                
                fulfillment.process_success(
                    correlation_id=payment.provider_reference,
                    provider_ref=query_res.get("provider_ref", ""),
                    amount=payment.amount,
                    metadata=meta_payload
                )
                
                # Refresh payment to reflect success status
                db.refresh(payment)
            elif query_res.get("status") == "failed":
                # Only fail if explicitly cancelled or confirmed failed, to avoid premature failure on pending/timeouts
                raw_status = query_res.get("raw_status", "")
                if "cancel" in raw_status.lower() or "failed" in raw_status.lower():
                    payment.status = "failed"
                    db.commit()
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
    
    name = f"{user.first_name} {user.last_name}" if user else "KapuLetu User"
    
    from services.reporting.pdf_gen import generate_receipt_pdf
    date_str = payment.created_at.strftime('%B %d, %Y') if payment.created_at else ""
    
    pdf_bytes = generate_receipt_pdf(str(payment.payment_id), plan.name, payment.amount, payment.provider_reference or "-", date_str, name)
    
    from fastapi.responses import Response
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=receipt_{payment.provider_reference}.pdf"})

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

@router.post("/webhook/flutterwave", summary="Flutterwave Webhook")
async def flutterwave_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    fulfillment = FulfillmentService(db)
    result = fulfillment.process_webhook("flutterwave", payload, request.headers)
    return {"status": result}

@router.post("/activate-trial", summary="Activate 21-Day Pro Trial")
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
        
    pro_plan = db.execute(select(Plan).where(Plan.name == "Professional")).scalars().first()
    if not pro_plan:
        raise HTTPException(status_code=500, detail="Professional plan not found in system")
        
    sub = db.execute(select(Subscription).where(Subscription.user_id == user_id)).scalars().first()
    
    if not sub:
        sub = Subscription(
            user_id=user_id,
            plan_id=pro_plan.plan_id,
            status="active",
            start_date=datetime.datetime.utcnow(),
            end_date=datetime.datetime.utcnow() + datetime.timedelta(days=21),
            is_auto_renew=False
        )
        db.add(sub)
    else:
        sub.plan_id = pro_plan.plan_id
        sub.status = "active"
        sub.start_date = datetime.datetime.utcnow()
        sub.end_date = datetime.datetime.utcnow() + datetime.timedelta(days=21)
        sub.is_auto_renew = False
        
    user.has_used_trial = True
    db.commit()
    
    # Send Trial Activation Email
    if user.email:
        try:
            from services.notifications.templates.render import render_email_template
            from services.notifications.tasks import send_email_task
            from models.communication_logs import CommunicationLog
            
            subject = f"Welcome to KapuLetu {pro_plan.name}!"
            html_body = render_email_template(
                "trial_started.html",
                name=user.first_name or "User",
                plan_name=pro_plan.name,
                expiry_date=sub.end_date.strftime('%B %d, %Y')
            )
            
            log = CommunicationLog(
                user_id=user.user_id,
                channel="EMAIL",
                destination=user.email,
                subject=subject,
                status="QUEUED"
            )
            db.add(log)
            db.commit()
            
            send_email_task.delay(str(log.log_id), user.email, subject, html_body)
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
        
    if not provider_svc.verify_webhook(body_str, dict(request.headers)):
        logger.error(f"WEBHOOK SIGNATURE INVALID for {provider}")
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    try:
        event_data = provider_svc.parse_webhook_payload(payload)
        logger.info(f"WEBHOOK PARSED EVENT DATA: {event_data}")
    except Exception as e:
        logger.error(f"WEBHOOK PARSE FAILED: {str(e)}")
        return {"received": True, "error": "parse_failed"}
        
    if event_data.get("success"):
        logger.info("WEBHOOK SUCCESS DETECTED. Starting fulfillment...")
        try:
            fulfillment = FulfillmentService(db)
            
            # Look up pending payment by correlation_id (CheckoutRequestID)
            correlation_id = event_data.get("correlation_id", "")
            logger.info(f"WEBHOOK LOOKING UP CORRELATION ID: {correlation_id}")
            
            pending_payment = db.execute(
                select(SubscriptionPayment).where(SubscriptionPayment.provider_reference == correlation_id)
            ).scalars().first()
            
            metadata = {}
            if pending_payment:
                logger.info(f"WEBHOOK FOUND PENDING PAYMENT: {pending_payment.payment_id}")
                metadata = dict(pending_payment.payment_metadata) if pending_payment.payment_metadata else {}
                metadata["user_id"] = str(pending_payment.user_id)
            else:
                logger.error(f"WEBHOOK COULD NOT FIND PENDING PAYMENT FOR CORRELATION {correlation_id}")
                
            fulfillment_result = fulfillment.process_success(
                correlation_id=correlation_id,
                provider_ref=event_data.get("provider_ref", ""),
                amount=event_data.get("amount", 0.0),
                metadata=metadata
            )
            logger.info(f"WEBHOOK FULFILLMENT RESULT: {fulfillment_result}")
        except Exception as e:
            logger.error(f"WEBHOOK FULFILLMENT CRASHED: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return {"received": True, "error": "fulfillment_crashed"}
    else:
        logger.warning(f"WEBHOOK REPORTED FAILURE: {event_data.get('raw_status')}")
        
    return {"received": True}
