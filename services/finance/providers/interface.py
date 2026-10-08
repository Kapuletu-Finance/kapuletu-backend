from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class PaymentProvider(ABC):
    """
    Abstract Base Class for all Payment Gateways (M-Pesa, Stripe, etc.)
    Ensures a consistent interface for the Subscription Engine.
    """
    
    @abstractmethod
    def initiate_checkout(self, user_id: str, plan_id: str, amount: float, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Starts the payment process with the gateway.
        Returns a correlation ID and any provider-specific data (e.g. STK prompt info or client_secret).
        """
        pass

    @abstractmethod
    def verify_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any], query_params: Optional[Dict[str, Any]] = None) -> bool:
        """
        Verifies that an incoming webhook really came from the gateway (signature, shared secret, etc.).
        """
        pass

    @abstractmethod
    def parse_webhook_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transforms a raw gateway callback into a unified 'KapuLetu Payment Event'.
        Returns: { 'success': bool, 'correlation_id': str, 'amount': float, 'provider_ref': str }
        """
        pass
