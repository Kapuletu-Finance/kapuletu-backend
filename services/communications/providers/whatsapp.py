"""
WhatsApp through the Meta Cloud API, using approved message templates.

Business-initiated messages outside the 24-hour customer-service window must be templates; a free-form text
broadcast is accepted by the API and then silently not delivered. Broadcasts therefore only send templates.
"""
import logging
import os
from typing import List

import httpx

from .base import SendResult, http_error, mock_sending_allowed

logger = logging.getLogger(__name__)

# Meta error codes worth retrying later: throughput limits and temporary outages
RETRYABLE_CODES = {4, 80007, 130429, 131000, 131016, 131056}


class WhatsAppProvider:
    name = "meta_whatsapp"

    def __init__(self):
        self.access_token = os.environ.get("META_ACCESS_TOKEN")
        self.phone_number_id = os.environ.get("META_PHONE_NUMBER_ID")
        self.api_version = os.environ.get("META_API_VERSION", "v23.0")

    def send_template(self, to_phone: str, template: str, language: str, params: List[str]) -> SendResult:
        if not self.access_token or not self.phone_number_id:
            if mock_sending_allowed():
                logger.warning(f"[MOCK WHATSAPP] to={to_phone} template={template} params={params}")
                return SendResult(ok=True, provider="mock", provider_message_id=f"mock-wa-{to_phone}")
            return SendResult(ok=False, provider=self.name, error="WhatsApp credentials are not configured")

        body = {"name": template, "language": {"code": language}}
        if params:
            body["components"] = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to_phone,
                   "type": "template", "template": body}
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        try:
            response = httpx.post(url, json=payload, headers={"Authorization": f"Bearer {self.access_token}"},
                                  timeout=15.0)
        except httpx.HTTPError as e:
            return SendResult(ok=False, provider=self.name, error=f"Network error: {e}", retryable=True)

        if response.status_code in (200, 201):
            messages = response.json().get("messages") or [{}]
            return SendResult(ok=True, provider=self.name, provider_message_id=messages[0].get("id"))

        result = http_error(self.name, response.status_code, response.text)
        try:
            error = response.json().get("error") or {}
            result.error = f"Meta error {error.get('code')}: {error.get('message')}"
            result.retryable = result.retryable or error.get("code") in RETRYABLE_CODES
        except ValueError:
            pass
        return result
