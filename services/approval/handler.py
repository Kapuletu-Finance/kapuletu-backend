import json
import logging
from common.database import SessionLocal
from common.decorators import with_auth, with_subscription_check
from services.approval.service import ApprovalService

logger = logging.getLogger(__name__)

@with_auth(role_required="treasurer")
@with_subscription_check(required_feature="approvals")
def handler(event, context):
    """
    Unified Transaction Approval & Review Handler.
    Routes requests based on the specific action (Approve, Split, Reject).
    """
    try:
        body = json.loads(event.get("body", "{}"))
        path = event.get("path", "")
        
        # 1. Context Extraction
        # pending_id can come from body or path parameter depending on route
        pending_id = body.get("pending_id") or event.get("pathParameters", {}).get("pending_id")
        group_id = body.get("group_id")
        user_id = event["user_id"]
        
        db = SessionLocal()
        service = ApprovalService(db)

        # 3. Action Routing
        try:
            if event.get("httpMethod") == "GET" and "/pending" in path:
                from repositories.transaction_repo import TransactionRepository
                repo = TransactionRepository(db)
                pendings = repo.fetch_pending_transactions_by_owner(user_id)
                
                import decimal
                from uuid import UUID
                from datetime import datetime
                
                def default_serializer(obj):
                    if isinstance(obj, UUID): return str(obj)
                    if isinstance(obj, decimal.Decimal): return float(obj)
                    if isinstance(obj, datetime): return obj.isoformat()
                    return str(obj)
                    
                results = [
                    {
                        "pending_id": p.pending_id,
                        "raw_message": p.raw_message,
                        "sender_name": p.sender_name,
                        "amount": p.amount,
                        "currency": p.currency,
                        "transaction_code": p.transaction_code,
                        "sender_phone": p.sender_phone,
                        "purpose": p.purpose,
                        "confidence_score": p.confidence_score,
                        "workflow_status": p.workflow_status,
                        "created_at": p.created_at
                    }
                    for p in pendings
                ]
                return {"statusCode": 200, "body": json.dumps({"results": results}, default=default_serializer)}

            elif event.get("httpMethod") == "GET" and "/history" in path:
                from repositories.transaction_repo import TransactionRepository
                repo = TransactionRepository(db)
                qs = event.get("queryStringParameters") or {}
                skip = int(qs.get("skip", 0))
                limit = int(qs.get("limit", 10))
                status_val = qs.get("status")
                search = qs.get("search")
                date_from = qs.get("date_from")
                date_to = qs.get("date_to")
                
                results, total = repo.fetch_inbox_history(
                    user_id, skip, limit, status_val, search, date_from, date_to
                )
                
                import decimal
                from uuid import UUID
                from datetime import datetime
                
                def default_serializer(obj):
                    if isinstance(obj, UUID): return str(obj)
                    if isinstance(obj, decimal.Decimal): return float(obj)
                    if isinstance(obj, datetime): return obj.isoformat()
                    return str(obj)

                formatted = []
                for r in results:
                    p = r["pending"]
                    formatted.append({
                        "pending_id": p.pending_id,
                        "sender_name": p.sender_name,
                        "sender_phone": p.sender_phone,
                        "amount": p.amount,
                        "currency": p.currency,
                        "transaction_code": p.transaction_code,
                        "purpose": p.purpose,
                        "workflow_status": p.workflow_status,
                        "processed_at": p.processed_at,
                        "processed_by_name": r["processed_by_name"],
                        "rejection_reason": p.rejection_reason,
                        "created_at": p.created_at
                    })
                    
                import math
                return {"statusCode": 200, "body": json.dumps({
                    "items": formatted,
                    "total_items": total,
                    "total_pages": math.ceil(total / limit) if total > 0 else 1,
                    "page": (skip // limit) + 1,
                    "limit": limit
                }, default=default_serializer)}

            if "/bulk/approve" in path:
                pending_ids = body.get("pending_ids", [])
                result = service.bulk_approve(pending_ids, user_id, group_id, body.get("campaign_id"))
                return {"statusCode": 200, "body": json.dumps({"results": result})}
            
            elif "/bulk/reject" in path:
                pending_ids = body.get("pending_ids", [])
                result = service.bulk_reject(pending_ids, user_id)
                return {"statusCode": 200, "body": json.dumps({"results": result})}

            elif "/approve" in path:
                if not pending_id: return {"statusCode": 400, "body": json.dumps({"error": "Missing pending_id"})}
                txn = service.approve_transaction(pending_id, user_id, group_id, body.get("campaign_id"))
                msg = "Transaction approved and committed to ledger."
            
            elif "/split" in path:
                if not pending_id: return {"statusCode": 400, "body": json.dumps({"error": "Missing pending_id"})}
                allocations = body.get("allocations", [])
                if not allocations:
                    return {"statusCode": 400, "body": json.dumps({"error": "Missing allocations for split"})}
                txn = service.split_transaction(pending_id, user_id, group_id, allocations, body.get("campaign_id"))
                msg = "Transaction split and committed to ledger."
            
            elif "/reject" in path:
                if not pending_id: return {"statusCode": 400, "body": json.dumps({"error": "Missing pending_id"})}
                reason = body.get("internal_note")
                service.reject_transaction(pending_id, user_id, reason)
                msg = "Transaction rejected."
                txn = None
                
            elif "/undo" in path:
                if not pending_id: return {"statusCode": 400, "body": json.dumps({"error": "Missing pending_id"})}
                pending = service.undo_rejection(pending_id, user_id)
                msg = "Rejection undone."
                txn = None
            
            else:
                return {"statusCode": 404, "body": json.dumps({"error": "Unknown approval action"})}

            return {
                "statusCode": 200,
                "body": json.dumps({
                    "message": msg,
                    "transaction_id": str(txn.transaction_id) if txn else None
                })
            }

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Approval Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
