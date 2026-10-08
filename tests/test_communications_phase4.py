"""
Communications phase 4: transactional mail through the outbox, staff alerts, sign-in code logging, website
inquiry replies, the preference centre, and escaping in support emails.
"""
import base64
import datetime

import pytest
from test_communications_phase1 import (  # noqa: F401  (Session is a fixture)
    COMM_MODELS,
    NOW,
    FakeEmail,
    Session,
    dispatcher,
    email_broadcast,
    person,
)

import services.notifications.admin_dispatcher as admin_dispatcher
from models.audit_log import AuditLog
from models.communications import CommMessage, CommSuppression
from models.contact_message import ContactMessage, ContactMessageReply
from models.system_config import SystemConfig
from services.communications import dispatcher as dispatcher_module
from services.communications import outbox
from services.communications.broadcasts import BroadcastService
from services.communications.common import CommError
from services.communications.consent import add_suppression
from services.communications.events import apply_events, resend_event
from services.communications.inquiries import InquiryService
from services.communications.outbox import queue_email, record_sent
from services.communications.preferences import get_preferences, update_preferences
from services.communications.providers import SendResult

# conftest replaces notify_admins_async for every test; keep the real one for the test that needs it
REAL_NOTIFY_ADMINS = admin_dispatcher.notify_admins_async


@pytest.fixture
def Session(Session):  # noqa: F811  (the communications schema plus website inquiries)
    engine = Session.kw["bind"]
    for model in COMM_MODELS + (ContactMessage, ContactMessageReply):
        model.__table__.create(engine, checkfirst=True)
    return Session


class FakeEmailWithFiles(FakeEmail):
    def __init__(self):
        super().__init__()
        self.singles = []

    def send_one(self, envelope):
        self.singles.append(envelope)
        return SendResult(ok=True, provider="fake", provider_message_id=f"single-{envelope.to}")


# --- the outbox API ---

def test_queue_email_waits_for_commit_then_wakes_the_dispatcher(db, monkeypatch):
    woken = []
    monkeypatch.setattr(dispatcher_module, "wake", lambda: woken.append(1))
    m = queue_email(db, "Ann@X.ke", "Your receipt", "<p>Paid</p>", kind="payment_receipt")
    assert (m.status, m.priority, m.destination, m.broadcast_id) == ("queued", 0, "ann@x.ke", None)
    assert woken == []
    db.commit()
    assert woken == [1]
    db.commit()
    assert woken == [1]  # once per transaction that queued mail

    with pytest.raises(CommError):
        queue_email(db, "not-an-address", "x", "y", kind="x")
    with pytest.raises(CommError):
        queue_email(db, "a@x.ke", "x", "y", kind="x", category="marketing")


def test_suppressed_addresses_get_service_mail_but_not_security_mail(db):
    add_suppression(db, "email", "gone@x.ke", "hard_bounce")
    receipt = queue_email(db, "gone@x.ke", "Receipt", "<p>x</p>", kind="payment_receipt")
    alert = queue_email(db, "gone@x.ke", "Password changed", "<p>x</p>", kind="password_changed", category="security")
    assert (receipt.status, alert.status) == ("suppressed", "queued")


def test_transactional_mail_goes_before_a_broadcast_and_is_wrapped(db):
    for _ in range(3):
        person(db)
    BroadcastService(db).create(email_broadcast(), None)
    d = dispatcher(db)
    d.start_due_broadcasts()
    queue_email(db, "vip@x.ke", "Your receipt", "<p>Paid <b>KES 1,000</b></p>", kind="payment_receipt")
    queue_email(db, "raw@x.ke", "Invite", "<html><body>Own layout</body></html>", kind="platform_invite", layout=False)
    db.commit()

    claimed = d._claim(2)
    assert {m.destination for m in claimed} == {"vip@x.ke", "raw@x.ke"}  # priority 0 jumps the queue
    for m in claimed:
        m.status, m.attempts = "queued", 0
    db.commit()

    email = FakeEmail()
    dispatcher(db, email).run_once()
    envelopes = {e.to: e for batch in email.batches for e in batch}
    assert "Paid <b>KES 1,000</b>" in envelopes["vip@x.ke"].html and "<html" in envelopes["vip@x.ke"].html.lower()
    assert envelopes["vip@x.ke"].text.startswith("Paid KES 1,000")
    assert envelopes["raw@x.ke"].html == "<html><body>Own layout</body></html>"  # not framed twice
    assert db.query(CommMessage).filter(CommMessage.status == "sent").count() == 5


def test_attachments_are_sent_one_at_a_time(db):
    pdf = [{"filename": "report.pdf", "content": base64.b64encode(b"%PDF").decode()}]
    queue_email(db, "cfo@x.ke", "Report", "<p>Attached</p>", kind="finance_report", attachments=pdf)
    queue_email(db, "a@x.ke", "Plain", "<p>x</p>", kind="x")
    db.commit()
    email = FakeEmailWithFiles()
    dispatcher(db, email).run_once()
    assert [e.to for e in email.singles] == ["cfo@x.ke"] and email.singles[0].attachments == pdf
    assert [e.to for batch in email.batches for e in batch] == ["a@x.ke"]
    assert db.query(CommMessage).filter_by(destination="cfo@x.ke").one().provider_message_id == "single-cfo@x.ke"


def test_record_sent_puts_synchronous_sends_in_the_log_and_tracks_them(db):
    record_sent(db, channel="email", destination="Ann@x.ke", kind="verification_code", subject="Your code",
                result=SendResult(ok=True, provider="resend", provider_message_id="re_1"))
    record_sent(db, channel="sms", destination="+254 700", kind="verification_code",
                result=SendResult(ok=False, provider="africastalking", error="timeout"))
    db.commit()
    rows = {m.channel: m for m in db.query(CommMessage)}
    assert (rows["email"].status, rows["sms"].status, rows["sms"].error) == ("sent", "failed", "timeout")
    apply_events(db, [resend_event({"type": "email.delivered", "data": {"email_id": "re_1", "to": ["ann@x.ke"]}}, "e1")])
    db.refresh(rows["email"])
    assert rows["email"].status == "delivered"


def test_delivery_log_kind_filter(db):
    person(db)
    BroadcastService(db).create(email_broadcast(), None)
    dispatcher(db).run_once()
    queue_email(db, "a@x.ke", "Receipt", "<p>x</p>", kind="payment_receipt")
    db.commit()
    svc = BroadcastService(db)
    assert [m["kind"] for m in svc.messages(kind="transactional")["items"]] == ["payment_receipt"]
    assert svc.messages(kind="broadcast")["total"] == 1
    with pytest.raises(CommError):
        svc.messages(kind="other")


# --- staff alerts ---

def test_staff_alerts_are_queued_to_the_configured_list(db, Session, monkeypatch):
    db.add(SystemConfig(config_key="admin_notification_emails", config_value={"emails": ["ops@x.ke"]}))
    db.add(SystemConfig(config_key="admin_notification_emails_finance", config_value={"emails": ["cfo@x.ke", "bad"]}))
    db.commit()
    monkeypatch.setattr(admin_dispatcher, "SessionLocal", Session)
    REAL_NOTIFY_ADMINS("Refund requested", "<p>KES 500</p>", category="finance")
    REAL_NOTIFY_ADMINS("New signup", "<p>x</p>", category="signups")  # no list of its own: general list
    sent = {(m.destination, m.context["kind"]) for m in db.query(CommMessage)}
    assert sent == {("cfo@x.ke", "staff_alert_finance"), ("ops@x.ke", "staff_alert_signups")}


# --- sign-in codes ---

def test_code_sends_are_logged_without_the_code(db, Session, monkeypatch):
    from services.auth import auth_service
    monkeypatch.setattr(auth_service, "SessionLocal", Session)
    auth_service.AuthService._log_code_send("email", "ann@x.ke", True, "resend", "re_9", subject="Your 2FA Verification Code")
    m = db.query(CommMessage).one()
    assert (m.context, m.subject, m.category) == ({"kind": "verification_code"}, "Your 2FA Verification Code", "security")


# --- inquiries ---

def make_inquiry(db, **kw):
    m = ContactMessage(first_name=kw.get("first_name", "Jane"), last_name="Doe", email="jane@x.ke",
                       topic=kw.get("topic", "Pricing"), message=kw.get("message", "How much is Silver?"),
                       status="unread")
    db.add(m)
    db.commit()
    return m


def test_reply_to_an_inquiry(db):
    staff = person(db, "Grace", role="support_agent")
    inquiry = make_inquiry(db, first_name="<b>Jane</b>", message="Is it <script>x</script>?")
    svc = InquiryService(db)
    assert svc.list()["unread"] == 1

    out = svc.reply(inquiry.id, "Silver is KES 1,000 a month.\nThanks!", staff.user_id)
    assert out["status"] == "replied" and len(out["thread"]) == 1
    assert out["thread"][0]["author"] == "Grace Test" and out["thread"][0]["delivery_status"] == "queued"

    m = db.query(CommMessage).one()
    html_body = m.context["html"]
    assert (m.destination, m.subject, m.context["kind"]) == ("jane@x.ke", "Re: Pricing", "inquiry_reply")
    assert "&lt;b&gt;Jane&lt;/b&gt;" in html_body and "<script>" not in html_body
    assert "Silver is KES 1,000 a month.<br>Thanks!" in html_body and "Grace Test" in html_body
    assert db.query(AuditLog).filter_by(action="INQUIRY_REPLIED").count() == 1

    assert svc.reply(inquiry.id, "Following up", staff.user_id, resolve=True)["status"] == "resolved"
    with pytest.raises(CommError):
        svc.reply(inquiry.id, "   ", staff.user_id)
    with pytest.raises(CommError):
        svc.set_status(inquiry.id, "archived", staff.user_id)
    assert svc.list(status="resolved")["total"] == 1


# --- preference centre ---

def test_preferences_per_channel(db):
    u = person(db, consent=False, email="pat@x.ke", phone="254700000123")
    assert get_preferences(db, u)["marketing"] == {"email": False, "whatsapp": False}

    out = update_preferences(db, u, email=True)
    assert out["marketing"] == {"email": True, "whatsapp": False} and u.marketing_consent is True
    # WhatsApp stays off through a marketing suppression on the number
    assert db.query(CommSuppression).filter_by(channel="whatsapp", destination="254700000123").one().reason == "unsubscribed"

    assert update_preferences(db, u, whatsapp=True)["marketing"] == {"email": True, "whatsapp": True}
    assert db.query(CommSuppression).count() == 0
    assert update_preferences(db, u, email=False, whatsapp=False)["marketing"] == {"email": False, "whatsapp": False}
    assert u.marketing_consent is False
    assert db.query(AuditLog).filter_by(action="MARKETING_PREFERENCES_CHANGED").count() == 3


def test_opting_back_in_lifts_a_complaint_but_not_a_bounce(db):
    u = person(db, email="pat@x.ke")
    add_suppression(db, "email", "pat@x.ke", "complaint", category="marketing")
    db.commit()
    assert get_preferences(db, u)["marketing"]["email"] is False
    assert update_preferences(db, u, email=True)["marketing"]["email"] is True

    add_suppression(db, "email", "pat@x.ke", "hard_bounce")
    db.commit()
    assert get_preferences(db, u)["email_blocked"] is True
    update_preferences(db, u, email=False)
    with pytest.raises(CommError, match="bounced"):
        update_preferences(db, u, email=True)


# --- support emails ---

def test_support_templates_escape_and_link_to_the_app():
    from services.notifications.email_templates import get_ticket_created_template, get_ticket_reply_template
    page = get_ticket_reply_template('<img src=x onerror="steal()">', "Line one\n<a href='evil'>click</a>", "Eve")
    assert "<img" not in page and "<a href='evil'>" not in page and "Line one<br>" in page
    assert "app.kapuletu.com" not in get_ticket_created_template("Ann", "Help", "t-1")


def test_contact_form_escapes_and_queues(db, monkeypatch):
    from services.support import router as support_router
    from services.support.schemas import ContactMessageCreate
    alerts = []
    monkeypatch.setattr(admin_dispatcher, "notify_admins_async", lambda **kw: alerts.append(kw))
    support_router.submit_contact_form(ContactMessageCreate(
        first_name="<a href='http://evil'>Win</a>", last_name="X", email="victim@x.ke", topic="Hi",
        message="Click <a href='http://evil'>here</a>"), db)
    m = db.query(CommMessage).one()
    assert m.destination == "victim@x.ke" and "<a href='http://evil'>" not in m.context["html"]
    assert "&lt;a href=" in m.context["html"]
    assert "<a href='http://evil'>" not in alerts[0]["html_content"]
