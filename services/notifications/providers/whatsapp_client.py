import os
import httpx
import logging

logger = logging.getLogger(__name__)

class WhatsAppClient:
    """
    A lightweight HTTP client for the WhatsApp Meta Cloud API.
    """
    def __init__(self):
        self.access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
        self.phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
        self.api_version = os.environ.get("WHATSAPP_API_VERSION", "v17.0")

    def send_text_message(self, to_phone: str, message: str) -> bool:
        if not self.access_token or not self.phone_number_id:
            logger.error("WhatsApp credentials are not set. Cannot send message.")
            return False

        # Clean phone number: remove any non-digit characters. 
        # Meta API requires country code without '+', e.g., '254700000000'
        clean_phone = ''.join(filter(str.isdigit, str(to_phone)))

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": clean_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message
            }
        }

        try:
            with httpx.Client() as client:
                response = client.post(url, headers=headers, json=payload, timeout=10.0)
                if response.status_code in (200, 201):
                    logger.info(f"Successfully dispatched WhatsApp message to {clean_phone}")
                    return True
                else:
                    logger.error(f"WhatsApp API error: {response.status_code} - {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send WhatsApp message: {e}")
            return False
