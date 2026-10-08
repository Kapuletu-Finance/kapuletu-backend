"""Email through Resend's batch endpoint: up to 100 emails per request, one idempotency key per batch."""
import hashlib
import logging
import os
from typing import List

import httpx

from .base import EmailEnvelope, SendResult, http_error, mock_sending_allowed

logger = logging.getLogger(__name__)

BATCH_URL = "https://api.resend.com/emails/batch"
MAX_BATCH = 100


class ResendEmailProvider:
    name = "resend"

    def __init__(self):
        self.api_key = os.environ.get("RESEND_API_KEY")
        self.sender = os.environ.get("BROADCAST_FROM_EMAIL") or os.environ.get(
            "DEFAULT_FROM_EMAIL", "KapuLetu <noreply@kapuletu.co.ke>")
        self.reply_to = os.environ.get("BROADCAST_REPLY_TO", "support@kapuletu.co.ke")

    def send_batch(self, envelopes: List[EmailEnvelope]) -> List[SendResult]:
        """One result per envelope, in order. Resend accepts or rejects a batch as a whole."""
        assert len(envelopes) <= MAX_BATCH
        if not envelopes:
            return []
        if not self.api_key:
            if mock_sending_allowed():
                for e in envelopes:
                    logger.warning(f"[MOCK EMAIL] to={e.to} subject={e.subject!r}")
                return [SendResult(ok=True, provider="mock", provider_message_id=f"mock-{e.message_id}") for e in envelopes]
            return [SendResult(ok=False, provider=self.name, error="RESEND_API_KEY is not configured")] * len(envelopes)

        payload = [{
            "from": self.sender,
            "to": [e.to],
            "reply_to": self.reply_to,
            "subject": e.subject,
            "html": e.html,
            **({"text": e.text} if e.text else {}),
            **({"headers": e.headers} if e.headers else {}),
        } for e in envelopes]
        # Same messages -> same key, so a retry after a timeout cannot send the batch twice
        key = hashlib.sha256(",".join(e.message_id for e in envelopes).encode()).hexdigest()
        headers = {"Authorization": f"Bearer {self.api_key}", "Idempotency-Key": key}
        try:
            response = httpx.post(BATCH_URL, json=payload, headers=headers, timeout=30.0)
        except httpx.HTTPError as e:
            return [SendResult(ok=False, provider=self.name, error=f"Network error: {e}", retryable=True)] * len(envelopes)

        if response.status_code not in (200, 201):
            logger.error(f"Resend batch failed: {response.status_code} {response.text[:300]}")
            return [http_error(self.name, response.status_code, response.text)] * len(envelopes)

        ids = [item.get("id") for item in (response.json().get("data") or [])]
        return [SendResult(ok=True, provider=self.name, provider_message_id=ids[i] if i < len(ids) else None)
                for i in range(len(envelopes))]
