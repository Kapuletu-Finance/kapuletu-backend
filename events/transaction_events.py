from events.event_bus import emit_event

def handle_transaction_approved(transaction):
    """
    Hook called when a transaction is officially approved and committed to the ledger.
    
    This can be used to trigger downstream actions like:
    1. Sending WhatsApp notifications to the member.
    2. Updating group balance caches.
    3. Triggering webhook callbacks for 3rd party integrations.
    """
    emit_event("TRANSACTION_APPROVED", transaction)
