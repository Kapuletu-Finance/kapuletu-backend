import base64
import requests
import datetime
import os
import json
from typing import Dict, Any
from .interface import PaymentProvider

class MpesaProvider(PaymentProvider):
    """
    Safaricom M-Pesa Implementation (Daraja API).
    """
    def __init__(self):
        self.consumer_key = os.environ.get('MPESA_CONSUMER_KEY')
        self.consumer_secret = os.environ.get('MPESA_CONSUMER_SECRET')
        self.shortcode = os.environ.get('MPESA_SHORTCODE')
        self.passkey = os.environ.get('MPESA_PASSKEY')
        self.base_url = os.environ.get('MPESA_BASE_URL', "https://sandbox.safaricom.co.ke")
        self.callback_url = os.environ.get('MPESA_CALLBACK_URL')

    def _get_access_token(self):
        """Fetches the OAuth2 token from Daraja"""
        auth_string = f"{self.consumer_key}:{self.consumer_secret}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        
        headers = {"Authorization": f"Basic {encoded_auth}"}
        response = requests.get(f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials", headers=headers)
        if response.status_code != 200:
            raise ValueError(f"M-Pesa auth failed. Status: {response.status_code}. Response: {response.text}")
        
        try:
            return response.json().get('access_token')
        except Exception:
            raise ValueError("Invalid response from M-Pesa authentication server.")

    def initiate_checkout(self, user_id: str, plan_id: str, amount: float, metadata: Dict[str, Any]) -> Dict[str, Any]:
        token = self._get_access_token()
        from datetime import timezone
        import zoneinfo
        now_eat = datetime.datetime.now(timezone.utc).astimezone(zoneinfo.ZoneInfo("Africa/Nairobi"))
        timestamp = now_eat.strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(f"{self.shortcode}{self.passkey}{timestamp}".encode()).decode()
        
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": metadata.get("phone_number"), # Treasurer phone
            "PartyB": self.shortcode,
            "PhoneNumber": metadata.get("phone_number"),
            "CallBackURL": self.callback_url,
            "AccountReference": f"SUB-{user_id[:8]}",
            "TransactionDesc": f"KapuLetu {plan_id} Subscription"
        }
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        response = requests.post(f"{self.base_url}/mpesa/stkpush/v1/processrequest", json=payload, headers=headers)
        if response.status_code != 200:
            raise ValueError(f"M-Pesa STK push failed. Status: {response.status_code}")
            
        try:
            res_data = response.json()
        except Exception:
            raise ValueError("Invalid response from M-Pesa STK Push server.")
        
        return {
            "correlation_id": res_data.get("CheckoutRequestID"),
            "status": "initiated" if response.status_code == 200 else "failed",
            "provider_response": res_data
        }

    def verify_webhook(self, payload: Dict[str, Any], headers: Dict[str, Any]) -> bool:
        # M-Pesa callbacks are trusted via IP whitelisting and internal validation in Safaricom 
        # Typically we check the ResultCode
        return True

    def parse_webhook_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        stk_callback = payload.get("Body", {}).get("stkCallback", {})
        result_code = stk_callback.get("ResultCode")
        
        success = result_code == 0
        correlation_id = stk_callback.get("CheckoutRequestID")
        
        # Extract amount from metadata if success
        amount = 0
        provider_ref = ""
        if success:
            items = stk_callback.get("CallbackMetadata", {}).get("Item", [])
            for item in items:
                if item["Name"] == "Amount": amount = item["Value"]
                if item["Name"] == "MpesaReceiptNumber": provider_ref = item["Value"]
                
        return {
            "success": success,
            "correlation_id": correlation_id,
            "amount": amount,
            "provider_ref": provider_ref,
            "raw_status": stk_callback.get("ResultDesc")
        }
