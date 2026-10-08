"""
Email templates: the HTML files under services/notifications/templates, overridable by versions saved from the
admin hub (comm_template_versions), always rendered in Jinja's sandbox.

Templates are editable by employees, so they are untrusted code: the sandbox stops them reaching Python
internals (the old non-sandboxed renderer let `{{ cycler.__init__.__globals__.os... }}` run commands).
"""
import datetime
import logging
import os
from typing import Optional

from jinja2 import ChoiceLoader, FileSystemLoader, FunctionLoader, TemplateError
from jinja2.sandbox import ImmutableSandboxedEnvironment, SecurityError
from sqlalchemy import func
from sqlalchemy.orm import Session

from common.config import get_config
from models.communications import CommTemplateVersion
from models.users import User

from .common import CommError, as_uuid, audit, iso

logger = logging.getLogger(__name__)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EDITABLE_DIR = os.path.join(_ROOT, "services", "notifications", "templates")
LAYOUT_DIR = os.path.join(_ROOT, "templates")  # email_base.html, the branded wrapper for broadcasts
MAX_TEMPLATE_BYTES = 200_000

SAMPLE_CONTEXT = {
    "name": "Jane", "first_name": "Jane", "message": "This is a preview of your message.",
    "invite_url": "https://kapuletu.co.ke/sign-up?invite_token=preview",
}


def _saved_version(name: str):
    """The newest saved version of an editable template, or None so the file is used."""
    from common.database import SessionLocal
    if not os.path.exists(os.path.join(EDITABLE_DIR, name)):
        return None
    db = SessionLocal()
    try:
        row = (db.query(CommTemplateVersion.content).filter(CommTemplateVersion.template_name == name)
               .order_by(CommTemplateVersion.version.desc()).first())
        return (row.content, None, lambda: False) if row else None
    except Exception as e:  # never let a lookup failure stop an email; the file is a safe fallback
        logger.warning(f"Template override lookup failed for {name}: {e}")
        return None
    finally:
        db.close()


env = ImmutableSandboxedEnvironment(
    loader=ChoiceLoader([FunctionLoader(_saved_version), FileSystemLoader(EDITABLE_DIR), FileSystemLoader(LAYOUT_DIR)]),
    autoescape=False,  # existing templates are written for raw HTML context values
)


# The branded wrapper is not editable from the hub, so it never needs the database
layout_env = ImmutableSandboxedEnvironment(loader=FileSystemLoader(LAYOUT_DIR), autoescape=False)


def _globals() -> dict:
    return {"year": datetime.datetime.utcnow().year, "current_year": datetime.datetime.utcnow().year,
            "frontend_url": get_config().FRONTEND_URL.rstrip("/")}


def render_template(name: str, **context) -> str:
    return env.get_template(name).render(**{**_globals(), **context})


def render_source(source: str, **context) -> str:
    return env.from_string(source).render(**{**_globals(), **context})


def editable_names() -> list:
    return sorted(f for f in os.listdir(EDITABLE_DIR) if f.endswith(".html"))


def _check_name(name: str) -> str:
    if name not in editable_names():
        raise CommError("Template not found", 404)
    return name


class TemplateService:
    def __init__(self, db: Session):
        self.db = db

    def _latest(self, name: str) -> Optional[CommTemplateVersion]:
        return (self.db.query(CommTemplateVersion).filter(CommTemplateVersion.template_name == name)
                .order_by(CommTemplateVersion.version.desc()).first())

    def list(self) -> list:
        latest = dict(self.db.query(CommTemplateVersion.template_name, func.max(CommTemplateVersion.version))
                      .group_by(CommTemplateVersion.template_name).all())
        return [{"id": n, "name": n.removesuffix(".html").replace("_", " ").title(), "version": latest.get(n, 0)}
                for n in editable_names()]

    def get(self, name: str) -> dict:
        _check_name(name)
        latest = self._latest(name)
        if latest:
            content = latest.content
        else:
            with open(os.path.join(EDITABLE_DIR, name), encoding="utf-8") as f:
                content = f.read()
        versions = (self.db.query(CommTemplateVersion, User).outerjoin(User, CommTemplateVersion.created_by == User.user_id)
                    .filter(CommTemplateVersion.template_name == name)
                    .order_by(CommTemplateVersion.version.desc()).limit(50).all())
        return {
            "id": name,
            "content": content,
            "version": latest.version if latest else 0,
            "versions": [{
                "version": v.version, "note": v.note, "created_at": iso(v.created_at),
                "created_by": f"{u.first_name} {u.last_name}" if u else None,
            } for v, u in versions],
        }

    def validate(self, content: str) -> None:
        """Parses and test-renders a template in the sandbox; raises CommError with the reason if it is unsafe or broken."""
        if len(content.encode("utf-8")) > MAX_TEMPLATE_BYTES:
            raise CommError("Template is too large")
        try:
            render_source(content, **SAMPLE_CONTEXT)
        except SecurityError:
            raise CommError("Template uses an expression that is not allowed")
        except TemplateError as e:
            raise CommError(f"Template error: {e}")

    def save(self, name: str, content: str, note: Optional[str], actor_id) -> dict:
        _check_name(name)
        self.validate(content)
        latest = self._latest(name)
        version = CommTemplateVersion(template_name=name, version=(latest.version if latest else 0) + 1,
                                      content=content, note=note, created_by=as_uuid(actor_id))
        self.db.add(version)
        audit(self.db, actor_id, "EMAIL_TEMPLATE_SAVED", "EMAIL_TEMPLATE", name, {"version": version.version, "note": note})
        self.db.commit()
        return self.get(name)

    def restore(self, name: str, version: int, actor_id) -> dict:
        _check_name(name)
        old = self.db.query(CommTemplateVersion).filter_by(template_name=name, version=version).first()
        if not old:
            raise CommError("Version not found", 404)
        return self.save(name, old.content, f"Restored version {version}", actor_id)

    def preview(self, name: str, content: Optional[str] = None, message: Optional[str] = None) -> str:
        """Renders the saved template, or unsaved `content` from the editor, with sample values."""
        _check_name(name)
        context = {**SAMPLE_CONTEXT, **({"message": message} if message else {})}
        try:
            return render_source(content, **context) if content is not None else render_template(name, **context)
        except SecurityError:
            raise CommError("Template uses an expression that is not allowed")
        except TemplateError as e:
            raise CommError(f"Template error: {e}")
