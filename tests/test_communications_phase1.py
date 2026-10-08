"""
Communications phase 1: audience resolution with consent and suppression, the broadcast lifecycle and approvals,
the outbox dispatcher (batching, retries, crash recovery, cancellation), unsubscribe links, sandboxed templates
and permission gating.
"""
import datetime
import uuid

import pytest
from finance_support import FINANCE_MODELS
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.base import Base
from models.communications import CommBroadcast, CommMessage, CommMessageEvent, CommSuppression, CommTemplateVersion
from models.notification import Notification
from models.subscription import Plan, Subscription
from models.system_config import SystemConfig
from models.users import User
from models.whatsapp_blocklist import WhatsAppBlocklist
from services.communications import consent
from services.communications.audience import resolve
from services.communications.broadcasts import BroadcastService
from services.communications.common import CommError
from services.communications.dispatcher import Dispatcher
from services.communications.providers import SendResult

NOW = datetime.datetime(2026, 10, 8, 9, 0)
COMM_MODELS = tuple(dict.fromkeys(FINANCE_MODELS + (
    Notification, WhatsAppBlocklist, CommBroadcast, CommMessage, CommMessageEvent, CommSuppression, CommTemplateVersion,
)))


@pytest.fixture
def Session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[m.__table__ for m in COMM_MODELS])
    return sessionmaker(bind=engine)


def person(db, first="Ann", consent=True, role="treasurer", email=None, phone=None, **kw):
    user = User(first_name=first, last_name="Test", email=email or f"{uuid.uuid4().hex[:8]}@x.ke",
                phone_number=phone or f"2547{uuid.uuid4().int % 10**8:08d}", slug=uuid.uuid4().hex[:10],
                role=role, marketing_consent=consent, **{"is_active": True, **kw})
    db.add(user)
    db.commit()
    return user


def email_broadcast(category="service", audience=None, channels=("email",), **extra):
    return {
        "title": "October update",
        "category": category,
        "audience": audience or {"type": "all_users"},
        "channels": list(channels),
        "content": {
            "email": {"subject": "Hi {{first_name}}", "html": "<p>Hello {{ first_name }}, news inside.</p>"},
            "whatsapp": {"template": "october_update", "language": "en", "params": ["{{first_name}}"]},
        },
        **extra,
    }


class FakeEmail:
    def __init__(self, outcome=None):
        self.batches = []
        self.outcome = outcome or (lambda e: SendResult(ok=True, provider="fake", provider_message_id=f"id-{e.to}"))

    def send_batch(self, envelopes):
        self.batches.append(envelopes)
        return [self.outcome(e) for e in envelopes]


class FakeWhatsApp:
    def __init__(self):
        self.sent = []

    def send_template(self, to, template, language, params):
        self.sent.append((to, template, language, params))
        return SendResult(ok=True, provider="fake_wa", provider_message_id=f"wamid-{to}")


def dispatcher(db, email=None, whatsapp=None, at=NOW):
    return Dispatcher(db, email_provider=email or FakeEmail(), whatsapp_provider=whatsapp or FakeWhatsApp(),
                      clock=lambda: at, sleep=lambda s: None)


# --- audience ---

def test_marketing_respects_consent_suppression_and_dedupes(db):
    yes = person(db, "Yes")
    no = person(db, "No", consent=False)
    blocked = person(db, "Blocked")
    person(db, "Gone", is_active=False)
    person(db, "Deleted", deleted_at=NOW)
    consent.add_suppression(db, "email", blocked.email.upper(), "hard_bounce")
    db.commit()

    r = resolve(db, {"type": "all_users"}, ["email", "in_app"], "marketing")
    emails = {x.destination for x in r.recipients if x.channel == "email"}
    in_app = {x.destination for x in r.recipients if x.channel == "in_app"}

    assert emails == {yes.email}
    assert in_app == {str(yes.user_id), str(no.user_id), str(blocked.user_id)}  # in-product, no consent needed
    assert r.skipped["email"] == {"no_destination": 0, "no_consent": 1, "suppressed": 1}
    assert r.audience_size == 3

    # Service messages ignore consent but still honour global suppressions
    service = resolve(db, {"type": "all_users"}, ["email"], "service")
    assert {x.destination for x in service.recipients} == {yes.email, no.email}


def test_marketing_unsubscribe_only_blocks_marketing(db):
    u = person(db)
    consent.add_suppression(db, "email", u.email, "unsubscribed", category="marketing")
    db.commit()
    assert resolve(db, {"type": "all_users"}, ["email"], "marketing").recipients == []
    assert len(resolve(db, {"type": "all_users"}, ["email"], "service").recipients) == 1


def test_whatsapp_blocklist_is_respected(db):
    u = person(db, phone="+254 711 000 111")
    db.add(WhatsAppBlocklist(phone_number="254711000111", is_blocked=True))
    db.commit()
    r = resolve(db, {"type": "all_users"}, ["whatsapp"], "service")
    assert r.recipients == [] and r.skipped["whatsapp"]["suppressed"] == 1
    assert u.phone_number


def test_segments(db):
    customer = person(db, "Cust")
    staff = person(db, "Staff", role="support_agent")
    trial_user = person(db, "Trial")
    plan = Plan(code="silver", name="Silver", price=1000)
    db.add(plan)
    db.flush()
    db.add(Subscription(user_id=trial_user.user_id, plan_id=plan.plan_id, status="active", is_trial=True,
                        end_date=datetime.datetime.utcnow() + datetime.timedelta(days=5)))
    db.commit()

    def people(audience):
        return {r.user_id for r in resolve(db, audience, ["in_app"], "service").recipients}

    assert people({"type": "customers"}) == {customer.user_id, trial_user.user_id}
    assert people({"type": "staff"}) == {staff.user_id}
    assert people({"type": "subscription", "states": ["trial"]}) == {trial_user.user_id}
    assert people({"type": "selected_users", "user_ids": [str(staff.user_id)]}) == {staff.user_id}
    with pytest.raises(CommError):
        resolve(db, {"type": "everyone_ever"}, ["email"], "service")


# --- lifecycle ---

def test_content_validation(db):
    person(db)
    svc = BroadcastService(db)
    bad = email_broadcast()
    bad["content"]["email"]["html"] = "<p>Hi {{ password }}</p>"
    with pytest.raises(CommError, match="unknown placeholders"):
        svc.create(bad, None)
    no_template = email_broadcast(channels=["whatsapp"])
    no_template["content"]["whatsapp"]["template"] = "Hello there!"
    with pytest.raises(CommError, match="Meta-approved template"):
        svc.create(no_template, None)


def test_large_marketing_needs_a_second_person(db):
    author, approver = person(db, "Author", role="content_manager"), person(db, "Approver", role="admin")
    for _ in range(3):
        person(db)
    db.add(SystemConfig(config_key="comm_marketing_approval_threshold", config_value=2))
    db.commit()
    svc = BroadcastService(db)

    created = svc.create(email_broadcast("marketing"), author.user_id)
    assert created["status"] == "awaiting_approval"
    with pytest.raises(CommError, match="someone other than its author"):
        svc.approve(created["id"], author.user_id)
    assert svc.approve(created["id"], approver.user_id, "Looks good")["status"] == "queued"

    # Service announcements and small marketing sends go straight out
    assert svc.create(email_broadcast("service"), author.user_id)["status"] == "queued"
    small = email_broadcast("marketing", audience={"type": "selected_users", "user_ids": [str(approver.user_id)]})
    assert svc.create(small, author.user_id)["status"] == "queued"


def test_estimate_reports_reach_without_creating_anything(db):
    person(db)
    person(db, consent=False)
    out = BroadcastService(db).estimate(email_broadcast("marketing", channels=["email", "in_app"]))
    assert out["reachable_people"] == 2
    assert out["channels"]["email"]["deliverable"] == 1 and out["channels"]["email"]["no_consent"] == 1
    assert db.query(CommBroadcast).count() == 0


# --- dispatcher ---

def config_with(monkeypatch, module, **values):
    from common.config import get_config
    config = get_config()
    for key, value in values.items():
        setattr(config, key, value)
    monkeypatch.setattr(module, "get_config", lambda: config)


def test_broadcast_is_expanded_sent_and_completed(db, monkeypatch):
    import services.communications.dispatcher as dispatcher_module
    config_with(monkeypatch, dispatcher_module, PUBLIC_API_URL="https://api.example.test")
    hacker = person(db, first='<a href="https://evil.test">Win</a>')
    person(db, "Bob")
    created = BroadcastService(db).create(email_broadcast("marketing", channels=["email", "in_app", "whatsapp"]), None)
    email, wa = FakeEmail(), FakeWhatsApp()

    result = dispatcher(db, email, wa).run_once()
    assert result["broadcasts_started"] == 1 and result["messages_processed"] == 6
    assert result["broadcasts_completed"] == 1

    envelopes = email.batches[0]
    evil = next(e for e in envelopes if e.to == hacker.email)
    assert '<a href="https://evil.test">' not in evil.html and "&lt;a href=" in evil.html  # escaped in the body
    assert "/unsubscribe?token=" in evil.html
    assert evil.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert evil.headers["List-Unsubscribe"].startswith("<https://api.example.test/communications/unsubscribe?token=")
    assert {params[0] for _, _, _, params in wa.sent} == {hacker.first_name, "Bob"}  # plain text for WhatsApp
    assert db.query(Notification).filter_by(type="admin_broadcast").count() == 2

    detail = BroadcastService(db).get(created["id"])
    assert detail["status"] == "completed"
    assert detail["stats"]["channels"] == {"email": {"sent": 2}, "in_app": {"sent": 2}, "whatsapp": {"sent": 2}}
    assert db.query(CommMessage).filter(CommMessage.provider_message_id.isnot(None)).count() == 6

    # Running again sends nothing twice
    assert dispatcher(db, email, wa).run_once()["messages_processed"] == 0
    assert len(email.batches) == 1


def test_email_is_sent_in_batches_of_100(db):
    for _ in range(205):
        db.add(User(first_name="P", last_name="Q", email=f"{uuid.uuid4().hex}@x.ke", phone_number=uuid.uuid4().hex[:12],
                    slug=uuid.uuid4().hex[:10], is_active=True))
    db.commit()
    BroadcastService(db).create(email_broadcast(), None)
    email = FakeEmail()
    dispatcher(db, email).run_once()
    assert [len(b) for b in email.batches] == [100, 100, 5]


def test_transient_failures_retry_with_backoff_then_give_up(db):
    person(db)
    BroadcastService(db).create(email_broadcast(), None)
    flaky = FakeEmail(lambda e: SendResult(ok=False, provider="fake", error="HTTP 429", retryable=True))

    dispatcher(db, flaky).run_once()
    msg = db.query(CommMessage).one()
    assert (msg.status, msg.attempts, msg.next_attempt_at) == ("queued", 1, NOW + datetime.timedelta(seconds=30))

    # Not due yet: nothing happens
    dispatcher(db, flaky, at=NOW + datetime.timedelta(seconds=10)).run_once()
    assert db.query(CommMessage).one().attempts == 1

    at = NOW
    for _ in range(4):
        at += datetime.timedelta(hours=2)
        dispatcher(db, flaky, at=at).run_once()
    msg = db.query(CommMessage).one()
    assert (msg.status, msg.attempts, msg.error) == ("failed", 5, "HTTP 429")


def test_permanent_failure_is_not_retried(db):
    person(db)
    BroadcastService(db).create(email_broadcast(), None)
    dispatcher(db, FakeEmail(lambda e: SendResult(ok=False, provider="fake", error="HTTP 422: bad address"))).run_once()
    msg = db.query(CommMessage).one()
    assert (msg.status, msg.attempts) == ("failed", 1)
    assert db.query(CommBroadcast).one().status == "completed"


def test_messages_left_mid_send_by_a_dead_worker_are_resumed(db):
    person(db)
    BroadcastService(db).create(email_broadcast(), None)
    d = dispatcher(db)
    d.start_due_broadcasts()
    d._claim(10)  # claimed, then the process died
    assert db.query(CommMessage).one().status == "sending"

    email = FakeEmail()
    dispatcher(db, email, at=NOW + datetime.timedelta(minutes=20)).run_once()
    assert db.query(CommMessage).one().status == "sent"
    assert len(email.batches) == 1


def test_cancel_stops_unsent_messages(db):
    for _ in range(3):
        person(db)
    svc = BroadcastService(db)
    created = svc.create(email_broadcast(), None)
    dispatcher(db).start_due_broadcasts()
    out = svc.cancel(created["id"], None)
    assert out["status"] == "cancelled" and out["stats"]["channels"] == {"email": {"cancelled": 3}}
    email = FakeEmail()
    dispatcher(db, email).run_once()
    assert email.batches == []
    with pytest.raises(CommError):
        svc.cancel(created["id"], None)


def test_scheduled_broadcast_waits_until_due(db):
    person(db)
    BroadcastService(db).create(email_broadcast(scheduled_for=datetime.datetime(2099, 1, 1)), None)
    assert dispatcher(db).run_once()["broadcasts_started"] == 0
    assert dispatcher(db, at=datetime.datetime(2099, 1, 1, 0, 1)).run_once()["messages_processed"] == 1


def test_unconfigured_email_provider_fails_outside_local(monkeypatch):
    import services.communications.providers.base as base
    from services.communications.providers import EmailEnvelope, ResendEmailProvider
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("COMM_MOCK_PROVIDERS", "false")
    config_with(monkeypatch, base, IS_LOCAL=False)
    [result] = ResendEmailProvider().send_batch([EmailEnvelope("m1", "a@x.ke", "S", "<p>x</p>")])
    assert not result.ok and not result.retryable and "not configured" in result.error


# --- unsubscribe ---

def test_unsubscribe_link(db):
    u = person(db)
    token = consent.unsubscribe_token(u.user_id)
    with pytest.raises(CommError):
        consent.read_unsubscribe_token(token[:-2] + "xx")

    out = consent.unsubscribe(db, token)
    assert out["status"] == "unsubscribed" and out["email"].endswith("@x.ke") and "*" in out["email"]
    db.refresh(u)
    assert u.marketing_consent is False
    assert {(s.channel, s.category, s.reason) for s in db.query(CommSuppression)} == {
        ("email", "marketing", "unsubscribed"), ("whatsapp", "marketing", "unsubscribed")}
    consent.unsubscribe(db, token)  # clicking twice is fine
    assert db.query(CommSuppression).count() == 2

    row = db.query(CommSuppression).first()
    with pytest.raises(CommError, match="only be reversed by the person"):
        consent.remove_suppression(db, row.suppression_id, None)


# --- templates ---

def test_template_sandbox_blocks_code_execution(db, monkeypatch):
    import common.database
    from services.communications.templates import TemplateService
    monkeypatch.setattr(common.database, "SessionLocal", lambda: db.__class__(bind=db.get_bind()))
    svc = TemplateService(db)

    for payload in ("{{ cycler.__init__.__globals__.os.popen('id').read() }}",
                    "{{ ''.__class__.__mro__[1].__subclasses__() }}"):
        with pytest.raises(CommError, match="not allowed"):
            svc.save("invite.html", payload, None, None)
        with pytest.raises(CommError, match="not allowed"):
            svc.preview("invite.html", content=payload)
    with pytest.raises(CommError, match="Template not found"):
        svc.save("../../local_server.py", "x", None, None)

    saved = svc.save("invite.html", "<p>Hi {{ message }}</p>", "Shorter copy", None)
    assert saved["version"] == 1 and saved["versions"][0]["note"] == "Shorter copy"
    from services.notifications.templates.render import render_email_template
    assert render_email_template("invite.html", message="there") == "<p>Hi there</p>"  # override wins
    assert svc.restore("invite.html", 1, None)["version"] == 2


# --- wiring ---

def test_every_admin_route_requires_manage_communications():
    """Inquiries also admit support staff (inquiry_handler); everything else needs manage_communications."""
    from services.communications.router import communicator, inquiry_handler, router
    for route in router.routes:
        deps = [d.call for d in route.dependant.dependencies]
        gate = inquiry_handler if "/inquiries" in route.path else communicator
        assert gate in deps, f"{route.path} is not gated"


def test_clear_all_notifications_is_reachable():
    from services.notifications.router import router
    deletes = [r.path for r in router.routes if "DELETE" in r.methods]
    assert deletes.index("/notifications/clear-all") < deletes.index("/notifications/{notification_id}")


def test_slow_sends_keep_their_claim(db):
    """A long WhatsApp pass renews its claim, so another worker's stale sweep can't re-send its messages."""
    for _ in range(45):
        person(db)
    BroadcastService(db).create(email_broadcast(channels=["whatsapp"]), None)
    clock = {"at": NOW}
    sweeps = []

    class SlowWhatsApp(FakeWhatsApp):
        def send_template(self, *args):
            clock["at"] += datetime.timedelta(minutes=1)  # each send takes a minute
            if len(self.sent) == 30:  # half an hour in, another worker sweeps for dead claims
                sweeps.append(dispatcher(db, at=clock["at"]).reclaim_stale())
            return super().send_template(*args)

    wa = SlowWhatsApp()
    Dispatcher(db, email_provider=FakeEmail(), whatsapp_provider=wa, clock=lambda: clock["at"],
               sleep=lambda s: None).run_once()
    assert sweeps == [0]
    assert len(wa.sent) == 45 and len({to for to, *_ in wa.sent}) == 45
