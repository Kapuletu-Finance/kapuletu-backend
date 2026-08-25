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
        self.base_url = os.environ.get('MPESA_BASE_URL', "https://sandbox.safaricom.co.ke").rstrip('/')
        self.callback_url = os.environ.get('MPESA_CALLBACK_URL')

    def _get_access_token(self):
        """Fetches the OAuth2 token from Daraja"""
        c_key = self.consumer_key.strip() if self.consumer_key else ""
        c_sec = self.consumer_secret.strip() if self.consumer_secret else ""
        auth_string = f"{c_key}:{c_sec}"
        encoded_auth = base64.b64encode(auth_string.encode()).decode()
        
        headers = {"Authorization": f"Basic {encoded_auth}"}
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Initiating M-Pesa Auth to: {url}")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            logger.info(f"M-Pesa Auth Response Code: {response.status_code}")
            logger.info(f"M-Pesa Auth Raw Response: {response.text}")
        except Exception as e:
            logger.error(f"M-Pesa Auth Connection Error: {str(e)}")
            raise ValueError(f"M-Pesa connection failed: {str(e)}")
            
        if response.status_code != 200:
            safe_key = c_key[:4] + "***" if len(c_key) > 4 else "EMPTY"
            raise ValueError(f"M-Pesa auth failed (Key: {safe_key}). Status: {response.status_code}. Response: {response.text}")
        
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
        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Initiating STK Push to: {url}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        logger.info(f"STK Push Response Code: {response.status_code}")
        logger.info(f"STK Push Raw Response: {response.text}")
        
        if response.status_code != 200:
            raise ValueError(f"M-Pesa STK push failed. Status: {response.status_code}. Response: {response.text}")
            
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

    def stk_push_query(self, checkout_request_id: str) -> Dict[str, Any]:
        """Queries Daraja API for the status of an STK push."""
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
            "CheckoutRequestID": checkout_request_id
        }
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"{self.base_url}/mpesa/stkpushquery/v1/query"
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Querying STK Push status for {checkout_request_id}")
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            logger.info(f"STK Push Query Response Code: {response.status_code}")
            logger.info(f"STK Push Query Raw: {response.text}")
            
            res_data = response.json()
            
            # Daraja API error format (e.g. invalid request)
            if response.status_code != 200:
                if res_data.get("errorCode") == "500.001.1001":
                    # Transaction is still processing
                    return {"success": False, "status": "pending", "raw_status": res_data.get("errorMessage")}
                return {"success": False, "status": "pending", "raw_status": res_data.get("errorMessage", "Query Failed")}
            
            # Success response format
            result_code = res_data.get("ResultCode")
            if result_code == "0":
                # Success
                return {
                    "success": True,
                    "status": "success",
                    "correlation_id": checkout_request_id,
                    "provider_ref": "", # Query API doesn't return receipt number reliably in all cases, but we can trust ResultCode 0
                    "raw_status": res_data.get("ResultDesc")
                }
            elif result_code:
                # E.g. 1032 for cancelled
                return {
                    "success": False,
                    "status": "failed",
                    "raw_status": res_data.get("ResultDesc")
                }
            else:
                return {"success": False, "status": "pending", "raw_status": "Unknown status"}
                
        except Exception as e:
            logger.error(f"STK Query Failed: {str(e)}")
            return {"success": False, "status": "pending", "error": str(e)}
