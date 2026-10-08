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
        self.default_from = os.environ.get("DEFAULT_FROM_EMAIL", "KapuLetu <noreply@kapuletu.co.ke>")
        self.base_url = "https://api.resend.com/emails"

    def send_email(self, to_email: str, subject: str, html_body: str, attachments: list = None) -> bool:
        """`attachments`: [{"filename": str, "content": base64 str}], as the Resend API takes them."""
        if not self.api_key:
            logger.warning(f"\n{'='*50}\n[MOCK EMAIL SENT to {to_email}]\nSubject: {subject}\n{'='*50}")
            # Extract and print link if it's an employee invite for easy local testing
            import re
            links = re.findall(r'href=[\'"]?([^\'" >]+)', html_body)
            if links:
                logger.warning(f"Found Links in Email: {links}")
            logger.warning(f"{'='*50}\nRESEND_API_KEY is not set. Email mocked as sent.")
            return True

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
        if attachments:
            payload["attachments"] = attachments

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
