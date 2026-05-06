from pydantic import BaseModel

class ApprovalSchema(BaseModel):
    """
    Pydantic Schema for Treasurer Approval Requests.
    
    Validates the payload when a treasurer approves or rejects a 
    pending transaction from the dashboard.
    """
    # The ID of the pending transaction being acted upon
    transaction_id: str
    # The action being performed (e.g., 'approve', 'reject', 'edit')
    action: str
