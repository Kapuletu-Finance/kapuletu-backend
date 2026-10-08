"""
Broadcast content: validation, personalization and the per-channel rendering of one message.

Broadcast bodies are written by employees in the rich-text editor. They are not Jinja templates: the only
dynamic parts are the placeholders below, substituted with values escaped for the target channel, so a
customer named `<a href=...>` cannot inject markup into mail sent from our domain.
"""
import datetime
import html
import re
from typing import Optional

from common.config import get_config

from .common import CHANNELS, CommError
from .templates import layout_env

PLACEHOLDERS = ("first_name", "last_name", "full_name", "email")
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_LANGUAGE = re.compile(r"^[a-z]{2}(_[A-Z]{2})?$")
_TEMPLATE_NAME = re.compile(r"^[a-z0-9_]{1,512}$")


def _check_placeholders(text: str, field: str) -> None:
    unknown = sorted({m for m in _PLACEHOLDER.findall(text or "") if m not in PLACEHOLDERS})
    if unknown:
        raise CommError(f"{field} uses unknown placeholders: {', '.join(unknown)}. "
                        f"Available: {', '.join(PLACEHOLDERS)}")


def html_to_text(value: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", value or "")
    text = re.sub(r"(?i)<li[^>]*>", "• ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def validate_content(channels: list, content: dict) -> dict:
    """Checks the content each chosen channel needs and returns it trimmed to those channels."""
    content = content or {}
    out = {}
    if not channels or any(c not in CHANNELS for c in channels):
        raise CommError(f"channels must be a non-empty list of {', '.join(CHANNELS)}")

    if "email" in channels:
        email = content.get("email") or {}
        subject, body = (email.get("subject") or "").strip(), (email.get("html") or "").strip()
        if not subject or not html_to_text(body):
            raise CommError("Email needs a subject and a body")
        if len(subject) > 200:
            raise CommError("Email subject must be at most 200 characters")
        _check_placeholders(subject, "Email subject")
        _check_placeholders(body, "Email body")
        out["email"] = {"subject": subject, "html": body, "preheader": (email.get("preheader") or "").strip()[:200]}

    if "in_app" in channels:
        in_app = content.get("in_app") or {}
        title = (in_app.get("title") or "").strip()
        body = (in_app.get("body") or "").strip()
        if not title or not body:
            raise CommError("In-app notification needs a title and a body")
        if len(title) > 120 or len(body) > 2000:
            raise CommError("In-app title must be at most 120 characters and body at most 2,000")
        _check_placeholders(title, "In-app title")
        _check_placeholders(body, "In-app body")
        out["in_app"] = {"title": title, "body": body}

    if "whatsapp" in channels:
        wa = content.get("whatsapp") or {}
        template, language = (wa.get("template") or "").strip(), (wa.get("language") or "en").strip()
        params = [str(p) for p in (wa.get("params") or [])]
        if not _TEMPLATE_NAME.match(template):
            raise CommError("WhatsApp needs the name of a Meta-approved template (lower-case letters, digits, _)")
        if not _LANGUAGE.match(language):
            raise CommError("WhatsApp template language must look like en or en_US")
        for i, p in enumerate(params, 1):
            _check_placeholders(p, f"WhatsApp parameter {i}")
        out["whatsapp"] = {"template": template, "language": language, "params": params}
    return out


def personalize(text: str, context: dict, escape: bool) -> str:
    def value(match):
        v = str(context.get(match.group(1), "") or "")
        return html.escape(v) if escape else v
    return _PLACEHOLDER.sub(value, text or "")


def recipient_context(first_name: str, last_name: str, email: str) -> dict:
    first_name, last_name = (first_name or "").strip(), (last_name or "").strip()
    return {
        "first_name": first_name or "there",
        "last_name": last_name,
        "full_name": f"{first_name} {last_name}".strip() or "there",
        "email": email or "",
    }


def render_email(content: dict, context: dict) -> tuple:
    """(subject, html) for one recipient, wrapped in the branded layout with an unsubscribe link for marketing."""
    subject = personalize(content["subject"], context, escape=False)
    body = personalize(content["html"], context, escape=True)
    page = layout_env.get_template("email_base.html").render(
        subject=html.escape(subject), body=body, preheader=html.escape(content.get("preheader") or ""),
        frontend_url=get_config().FRONTEND_URL.rstrip("/"), current_year=datetime.datetime.utcnow().year,
        unsubscribe_url=context.get("unsubscribe_url"),
    )
    return subject, page


def render_in_app(content: dict, context: dict) -> tuple:
    return personalize(content["title"], context, escape=False), personalize(content["body"], context, escape=False)


def render_whatsapp_params(content: dict, context: dict) -> list:
    return [personalize(p, context, escape=False) for p in content.get("params", [])]


def default_in_app(email_content: Optional[dict]) -> Optional[dict]:
    """In-app copy derived from the email when the composer didn't write separate copy."""
    if not email_content:
        return None
    return {"title": email_content["subject"][:120], "body": html_to_text(email_content["html"])[:2000]}
