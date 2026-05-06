from pydantic import BaseModel

class IngestionSchema(BaseModel):
    """
    Pydantic Schema for Inbound Webhook Validation.
    
    Ensures that the incoming request contains the minimum required fields
    to initiate the parsing and ingestion process.
    """
    # The raw text content of the message
    message: str
    # The sender's phone number in E.164 format
    phone: str
