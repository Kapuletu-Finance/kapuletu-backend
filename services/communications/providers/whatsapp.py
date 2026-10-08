"""
WhatsApp through the Meta Cloud API, using approved message templates.

Business-initiated messages outside the 24-hour customer-service window must be templates; a free-form text
broadcast is accepted by the API and then silently not delivered. Broadcasts therefore only send templates.
"""
import logging
import os
import re
import time
from typing import List, Optional

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


# --- approved template catalogue ---

_POSITIONAL = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_ANY_VARIABLE = re.compile(r"\{\{\s*[^}]+\s*\}\}")
_CACHE_SECONDS = 300
_cache: dict = {"at": 0.0, "templates": None}


def describe_template(raw: dict) -> dict:
    """
    Name, language, body text and how many body variables a Meta template takes, and whether broadcasts can
    send it. Broadcasts only fill body variables, so templates that also need header media, header variables,
    dynamic button URLs or named parameters are listed but marked unsendable.
    """
    body, problems = "", []
    for component in raw.get("components") or []:
        kind = (component.get("type") or "").upper()
        text = component.get("text") or ""
        if kind == "BODY":
            body = text
        elif kind == "HEADER":
            if (component.get("format") or "TEXT").upper() != "TEXT":
                problems.append("has a media header")
            elif _ANY_VARIABLE.search(text):
                problems.append("has a header variable")
        elif kind == "BUTTONS":
            for button in component.get("buttons") or []:
                if _ANY_VARIABLE.search(button.get("url") or ""):
                    problems.append("has a dynamic button link")
    positions = [int(n) for n in _POSITIONAL.findall(body)]
    if _ANY_VARIABLE.search(_POSITIONAL.sub("", body)):
        problems.append("uses named variables")
    return {
        "name": raw.get("name"),
        "language": raw.get("language"),
        "category": (raw.get("category") or "").lower(),
        "body": body,
        "variables": max(positions, default=0),
        "sendable": not problems,
        "unsupported_reason": ", ".join(dict.fromkeys(problems)) or None,
    }


def approved_templates(force: bool = False) -> Optional[List[dict]]:
    """
    Approved templates from Meta Business Manager, cached for five minutes. None when META_WABA_ID or the
    access token isn't configured, so callers can fall back to trusting the typed template name.
    """
    waba_id, token = os.environ.get("META_WABA_ID"), os.environ.get("META_ACCESS_TOKEN")
    if not waba_id or not token:
        return None
    if not force and _cache["templates"] is not None and time.time() - _cache["at"] < _CACHE_SECONDS:
        return _cache["templates"]
    version = os.environ.get("META_API_VERSION", "v23.0")
    url = f"https://graph.facebook.com/{version}/{waba_id}/message_templates"
    params = {"fields": "name,language,status,category,components", "limit": 200}
    templates = []
    try:
        while url:
            response = httpx.get(url, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=15.0)
            response.raise_for_status()
            page = response.json()
            templates += [describe_template(t) for t in page.get("data") or [] if t.get("status") == "APPROVED"]
            url, params = (page.get("paging") or {}).get("next"), None  # "next" already carries the query
    except (httpx.HTTPError, ValueError) as e:
        logger.error(f"Could not load WhatsApp templates from Meta: {e}")
        if _cache["templates"] is not None:
            return _cache["templates"]  # stale beats nothing
        raise
    templates.sort(key=lambda t: (t["name"], t["language"]))
    _cache.update(at=time.time(), templates=templates)
    return templates
