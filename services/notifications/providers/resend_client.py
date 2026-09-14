import os
import httpx
import logging

logger = logging.getLogger(__name__)

class ResendClient:
    """
    A lightweight HTTP client for the Resend Email API.
    Does not require the resend python SDK.
    """
    def __init__(self):
        self.api_key = os.environ.get("RESEND_API_KEY")
        self.default_from = os.environ.get("DEFAULT_FROM_EMAIL", "Kapuletu <noreply@kapuletu.com>")
        self.base_url = "https://api.resend.com/emails"

    def send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        if not self.api_key:
            logger.error("RESEND_API_KEY is not set. Cannot send email.")
            return False

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "from": self.default_from,
            "to": [to_email],
            "subject": subject,
            "html": html_body
        }

        try:
            with httpx.Client() as client:
                response = client.post(self.base_url, headers=headers, json=payload, timeout=10.0)
                if response.status_code in (200, 201):
                    logger.info(f"Successfully dispatched email to {to_email}")
                    return True
                else:
                    logger.error(f"Resend API error: {response.status_code} - {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send email via Resend: {e}")
            return False
