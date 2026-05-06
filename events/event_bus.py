def emit_event(event_type: str, data: any):
    """
    Simplified Event Bus for internal communication.
    
    This utility allows different services to decouple their logic by emitting
    signals when major state changes occur (e.g., Transaction Approved).
    
    In production, this would integrate with AWS EventBridge or SNS.
    """
    # Currently prints to CloudWatch logs; extensible to real event brokers.
    print(f"System Event Emitted: [{event_type}] -> Data: {data}")
