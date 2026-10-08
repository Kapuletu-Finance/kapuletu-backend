from services.communications.templates import render_template


def render_email_template(template_name: str, **context) -> str:
    """Renders an email template (saved override or file) in the sandbox; see services/communications/templates.py."""
    return render_template(template_name, **context)
