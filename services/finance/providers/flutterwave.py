import requests
import os
import uuid
from typing import Dict, Any
from .interface import PaymentProvider

class FlutterwaveProvider(PaymentProvider):
    """
    Flutterwave Payment Gateway Implementation.
    """
    def __init__(self):
        self.secret_key = os.environ.get('FLW_SECRET_KEY')
        self.public_key = os.environ.get('FLW_PUBLIC_KEY')
        self.secret_hash = os.environ.get('FLW_SECRET_HASH')
        self.base_url = "https://api.flutterwave.com/v3"

    def initiate_checkout(self, user_id: str, plan_id: str, amount: float, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Starts the Flutterwave payment process.
        """
        tx_ref = f"kp-{uuid.uuid4().hex[:12]}"
        
        payload = {
            "tx_ref": tx_ref,
            "amount": str(amount),
            "currency": os.environ.get('FLW_CURRENCY', 'KES'),
            "redirect_url": os.environ.get('FLW_REDIRECT_URL', 'https://app.kapuletu.com/payment/success'),
            "meta": {
                "user_id": user_id,
                "plan_id": plan_id,
                **metadata
            },
            "customer": {
                "email": metadata.get("email", "support@kapuletu.com"), # Email is required by Flutterwave
                "phonenumber": metadata.get("phone_number", ""),
                "name": metadata.get("name", "KapuLetu User")
            },
            "customizations": {
                "title": "KapuLetu Subscription",
                "description": f"Payment for {plan_id} plan",
                "logo": "https://app.kapuletu.com/logo.png"
            }
        }

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }

        try:
            response = requests.post(f"{self.base_url}/payments", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                return {
                    "correlation_id": tx_ref,
                    "status": "initiated",
                    "provider_response": {
                        "link": data["data"]["link"]
                    }
                }
            else:
                raise Exception(f"Flutterwave error: {data.get('message')}")
        except Exception as e:
            raise Exception(f"Failed to initiate Flutterwave checkout: {str(e)}")

    def verify_webhook(self, payload: str, headers: Dict[str, Any]) -> bool:
        """
        Verifies the Flutterwave signature using the secret hash.
        """
        # Flutterwave sends the secret hash in the 'verif-hash' header
        signature = headers.get('verif-hash') or headers.get('Verif-Hash')
        if not signature or not self.secret_hash:
            return False
        
        return signature == self.secret_hash

    def parse_webhook_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transforms Flutterwave callback into a unified KapuLetu Payment Event.
        """
        data = payload.get("data", {})
        status = payload.get("status") or data.get("status")
        
        # Flutterwave status can be 'successful' or 'failed'
        success = status == "successful"
        
        return {
            "success": success,
            "correlation_id": data.get("tx_ref"),
            "amount": float(data.get("amount", 0)),
            "provider_ref": str(data.get("id")),
            "raw_status": status
        }
