def validate_payload(payload: dict) -> bool:
    """
    Basic structural validation for the raw ingestion payload.
    
    Checks if the dictionary contains the mandatory 'message' and 'phone' fields.
    This is used as a fast-fail check before triggering more expensive parsing logic.
    """
    return "message" in payload and "phone" in payload
