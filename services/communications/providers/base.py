"""What every channel provider returns, and how unconfigured providers behave."""
import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from common.config import get_config


@dataclass
class SendResult:
    ok: bool
    provider: str
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    # True for rate limits, provider 5xx and network failures: the message is tried again later
    retryable: bool = False


@dataclass
class EmailEnvelope:
    message_id: str
    to: str
    subject: str
    html: str
    text: str = ""
    headers: Dict[str, str] = field(default_factory=dict)


def mock_sending_allowed() -> bool:
    """
    Without provider credentials, only local development may pretend to send. Anywhere else the message fails
    loudly, so a misconfigured deploy shows up as failures instead of silently "sent" mail.
    """
    return get_config().IS_LOCAL or os.getenv("COMM_MOCK_PROVIDERS", "false").lower() == "true"


def http_error(provider: str, status_code: int, body: str) -> SendResult:
    return SendResult(ok=False, provider=provider, error=f"HTTP {status_code}: {body[:500]}",
                      retryable=status_code == 429 or status_code >= 500)
