"""
Communications phase 3: provider webhooks (Resend via Svix, Meta via X-Hub-Signature-256), event ordering and
idempotency, automatic suppression, deliverability reporting and the CSV export.
"""
import base64
import datetime
import hashlib
import hmac
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_communications_phase1 import (  # noqa: F401  (Session is a fixture)
    FakeEmail,
    FakeWhatsApp,
    Session,
    dispatcher,
    email_broadcast,
    person,
)

from common.database import get_db
from models.communications import CommMessage, CommMessageEvent, CommSuppression
from services.communications import events
from services.communications.broadcasts import BroadcastService
from services.communications.common import CommError
from services.communications.events import (
    DeliveryEvent,
    apply_events,
    resend_event,
    verify_meta_signature,
    verify_resend_signature,
    whatsapp_events,
)

SECRET = "whsec_" + base64.b64encode(b"test-signing-key").decode()
T0 = datetime.datetime(2026, 10, 8, 9, 0)


def svix_headers(body: bytes, msg_id="msg_1", at=None, secret=SECRET):
    ts = str(int(at if at is not None else time.time()))
    key = base64.b64decode(secret.removeprefix("whsec_"))
    sig = base64.b64encode(hmac.new(key, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return {"svix-id": msg_id, "svix-timestamp": ts, "svix-signature": f"v1,bogus v1,{sig}"}


def resend_payload(kind, email_id, to, at=T0, **data):
    return {"type": f"email.{kind}", "created_at": at.isoformat() + "Z",
            "data": {"email_id": email_id, "to": [to], **data}}


def sent_broadcast(db, category="service", channels=("email",), people=1):
    users = [person(db) for _ in range(people)]
    email, wa = FakeEmail(), FakeWhatsApp()
    BroadcastService(db).create(email_broadcast(category, channels=list(channels)), None)
    dispatcher(db, email, wa).run_once()
    return users


def ev(kind, email_id, to, event_id, at=T0, **data):
    return resend_event(resend_payload(kind, email_id, to, at, **data), event_id)


# --- signatures ---

def test_resend_signature():
    body = b'{"type":"email.delivered"}'
    verify_resend_signature(body, svix_headers(body), SECRET)  # valid (second of two signatures)
    with pytest.raises(CommError, match="Invalid webhook signature"):
        verify_resend_signature(body + b" ", svix_headers(body), SECRET)
    with pytest.raises(CommError, match="too old"):
        verify_resend_signature(body, svix_headers(body, at=time.time() - 3600), SECRET)
    with pytest.raises(CommError, match="Missing"):
        verify_resend_signature(body, {}, SECRET)


def test_resend_webhook_needs_a_secret(monkeypatch):
    monkeypatch.delenv("RESEND_WEBHOOK_SECRET", raising=False)
    with pytest.raises(CommError) as e:
        verify_resend_signature(b"{}", svix_headers(b"{}"))
    assert e.value.status_code == 503


def test_meta_signature():
    body = b'{"entry":[]}'
    good = "sha256=" + hmac.new(b"appsecret", body, hashlib.sha256).hexdigest()
    assert verify_meta_signature(body, good, "appsecret")
    assert not verify_meta_signature(body + b"x", good, "appsecret")
    assert not verify_meta_signature(body, None, "appsecret")


# --- event mapping ---

def test_resend_event_mapping():
    hard = ev("bounced", "e1", "A@X.KE", "m1", bounce={"type": "Permanent", "subType": "General", "message": "No such user"})
    assert (hard.event, hard.destination, hard.suppress) == ("bounced", "a@x.ke", ("email", "all", "hard_bounce"))
    assert "No such user" in hard.detail
    soft = ev("bounced", "e1", "a@x.ke", "m2", bounce={"type": "Transient", "subType": "MailboxFull"})
    assert (soft.event, soft.suppress) == ("soft_bounced", None)
    complaint = ev("complained", "e1", "a@x.ke", "m3")
    assert complaint.suppress == ("email", "marketing", "complaint")
    assert ev("clicked", "e1", "a@x.ke", "m4", click={"link": "https://kapuletu.co.ke/pricing"}).detail == \
        "https://kapuletu.co.ke/pricing"
    assert resend_event({"type": "contact.created", "data": {}}, "m5") is None


# --- applying events ---

def test_events_move_status_forward_only_and_are_idempotent(db):
    [u] = sent_broadcast(db)
    pid = f"id-{u.email}"
    msg = db.query(CommMessage).one()

    # Opened arrives before delivered: still counts as delivered, at the earliest time seen
    assert apply_events(db, [ev("opened", pid, u.email, "e-open", at=T0 + datetime.timedelta(minutes=5))]) == 1
    assert apply_events(db, [ev("delivered", pid, u.email, "e-deliv", at=T0 + datetime.timedelta(minutes=1))]) == 1
    db.refresh(msg)
    assert msg.status == "delivered"
    assert msg.delivered_at == T0 + datetime.timedelta(minutes=1)
    assert msg.opened_at == T0 + datetime.timedelta(minutes=5)

    # Same webhook delivered twice: ignored
    assert apply_events(db, [ev("opened", pid, u.email, "e-open")]) == 0
    assert db.query(CommMessageEvent).count() == 2

    apply_events(db, [ev("clicked", pid, u.email, "e-click", at=T0 + datetime.timedelta(minutes=6),
                         click={"link": "https://x.ke"})])
    apply_events(db, [ev("complained", pid, u.email, "e-spam", at=T0 + datetime.timedelta(minutes=10))])
    # A late, redundant "delivered" can't undo the complaint
    apply_events(db, [ev("delivered", pid, u.email, "e-deliv-late", at=T0 + datetime.timedelta(minutes=11))])
    db.refresh(msg)
    assert (msg.status, msg.clicked_at is not None) == ("complained", True)
    assert {(s.channel, s.category, s.reason) for s in db.query(CommSuppression)} == {("email", "marketing", "complaint")}

    timeline = BroadcastService(db).message_events(msg.message_id)
    assert [e["event"] for e in timeline["events"]] == ["delivered", "opened", "clicked", "complained", "delivered"]


def test_hard_bounce_fails_the_message_and_suppresses(db):
    [u] = sent_broadcast(db)
    apply_events(db, [ev("bounced", f"id-{u.email}", u.email, "e1", bounce={"type": "Permanent", "message": "550 no user"})])
    msg = db.query(CommMessage).one()
    assert msg.status == "bounced" and "550 no user" in msg.error
    s = db.query(CommSuppression).one()
    assert (s.destination, s.category, s.reason, s.user_id) == (u.email, "all", "hard_bounce", u.user_id)

    # The next broadcast skips the address
    estimate = BroadcastService(db).estimate({"audience": {"type": "all_users"}, "channels": ["email"]})
    assert estimate["channels"]["email"]["suppressed"] == 1


def test_bounce_of_mail_sent_outside_the_outbox_still_suppresses(db):
    apply_events(db, [ev("bounced", "legacy-otp-id", "old@x.ke", "e1", bounce={"type": "Permanent"})])
    assert db.query(CommSuppression).one().destination == "old@x.ke"
    assert db.query(CommMessageEvent).one().message_id is None


def whatsapp_status(wamid, status, phone="254700000001", ts=1791450000, code=None):
    s = {"id": wamid, "status": status, "timestamp": str(ts), "recipient_id": phone}
    if code:
        s["errors"] = [{"code": code, "title": "x", "error_data": {"details": "User opted out of marketing"}}]
    return s


def test_whatsapp_statuses(db):
    users = sent_broadcast(db, "marketing", channels=["whatsapp"], people=2)
    wamids = {f"wamid-{u.phone_number}" for u in users}
    a, b = sorted(users, key=lambda u: u.phone_number)
    payload = {"entry": [
        {"changes": [{"value": {"statuses": [whatsapp_status(f"wamid-{a.phone_number}", "delivered", a.phone_number),
                                              whatsapp_status(f"wamid-{a.phone_number}", "read", a.phone_number)]}}]},
        {"changes": [{"value": {"statuses": [whatsapp_status(f"wamid-{b.phone_number}", "failed", b.phone_number,
                                                             code=131050)]}}]},
    ]}
    assert {e.provider_message_id for e in whatsapp_events(payload)} == wamids
    apply_events(db, whatsapp_events(payload))
    apply_events(db, whatsapp_events(payload))  # Meta retries: nothing changes

    by_phone = {m.destination: m for m in db.query(CommMessage)}
    read = by_phone[a.phone_number]
    assert read.status == "delivered" and read.opened_at is not None
    failed = by_phone[b.phone_number]
    assert failed.status == "failed" and "131050" in failed.error
    s = db.query(CommSuppression).one()
    assert (s.channel, s.category, s.reason) == ("whatsapp", "marketing", "unsubscribed")
    assert db.query(CommMessageEvent).count() == 3


# --- webhook routes ---

@pytest.fixture
def client(db, monkeypatch):
    from services.communications.router import public_router
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", SECRET)
    app = FastAPI()
    app.include_router(public_router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_resend_webhook_route(db, client):
    [u] = sent_broadcast(db)
    body = json.dumps(resend_payload("delivered", f"id-{u.email}", u.email)).encode()
    assert client.post("/communications/webhooks/resend", content=body, headers=svix_headers(body, "evt_1")).status_code == 200
    assert db.query(CommMessage).one().status == "delivered"
    forged = client.post("/communications/webhooks/resend", content=body,
                         headers=svix_headers(body, "evt_2", secret="whsec_" + base64.b64encode(b"wrong").decode()))
    assert forged.status_code == 401


def test_meta_webhook_rejects_unsigned_posts_when_secret_is_set(monkeypatch):
    from common.config import get_config
    from services.ingestion import handler
    config = get_config()
    config.META_APP_SECRET = "appsecret"
    monkeypatch.setattr(handler, "get_config", lambda: config)
    processed = []
    monkeypatch.setattr(handler, "process_ingestion", lambda body, conf: processed.append(body))

    body = '{"entry":[]}'
    unsigned = handler.handler({"httpMethod": "POST", "body": body, "headers": {}}, None)
    assert unsigned["statusCode"] == 403
    sig = "sha256=" + hmac.new(b"appsecret", body.encode(), hashlib.sha256).hexdigest()
    signed = handler.handler({"httpMethod": "POST", "body": body, "headers": {"X-Hub-Signature-256": sig}}, None)
    assert signed["statusCode"] == 200
    time.sleep(0.1)  # the handler processes in a thread
    assert processed == [body]


def test_whatsapp_statuses_ignored_without_app_secret(db, monkeypatch):
    from common.config import get_config
    from services.ingestion import handler
    config = get_config()
    config.META_APP_SECRET = ""
    called = []
    monkeypatch.setattr(events, "apply_events", lambda *a: called.append(a))
    handler.record_whatsapp_statuses({"entry": []}, config)
    assert called == []


# --- reporting ---

def test_broadcast_engagement_and_deliverability(db):
    users = sent_broadcast(db, people=4)
    a, b, c, d = users
    apply_events(db, [
        ev("delivered", f"id-{a.email}", a.email, "1"), ev("opened", f"id-{a.email}", a.email, "2"),
        ev("clicked", f"id-{a.email}", a.email, "3"),
        ev("delivered", f"id-{b.email}", b.email, "4"),
        ev("bounced", f"id-{c.email}", c.email, "5", bounce={"type": "Permanent"}),
    ])
    svc = BroadcastService(db)
    [row] = svc.list()["items"]
    assert row["stats"]["engagement"]["email"] == {"delivered": 2, "opened": 1, "clicked": 1}
    assert row["stats"]["channels"]["email"] == {"delivered": 2, "bounced": 1, "sent": 1}

    report = svc.deliverability(30)
    assert report["deliverability"]["email"] == {"attempted": 4, "delivered": 2, "opened": 1, "clicked": 1,
                                                 "bounced": 1, "complained": 0, "failed": 0}
    assert sum(day["attempted"] for day in report["daily"]) == 4
    assert len(report["daily"]) == 31 and report["tracking"] == {"email": True, "whatsapp": False}
    assert d.email  # d was sent but never reported on: stays "sent"


def test_export_filters_and_neutralises_formulas(db):
    u = person(db, first="=HYPERLINK(\"http://evil\")")
    BroadcastService(db).create(email_broadcast(), None)
    dispatcher(db).run_once()
    apply_events(db, [ev("opened", f"id-{u.email}", u.email, "1")])
    svc = BroadcastService(db)
    assert len(list(svc.export_messages(status="opened"))) == 1
    assert list(svc.export_messages(status="bounced")) == []

    from services.communications.router import _csv_cell
    [row] = list(svc.export_messages())
    assert _csv_cell(row["recipient"]).startswith("'=")
    assert _csv_cell("plain") == "plain"
    with pytest.raises(CommError):
        list(svc.export_messages(status="nonsense"))


def test_delivery_event_without_destination_does_not_suppress(db):
    apply_events(db, [DeliveryEvent(provider="resend", provider_event_id="x", provider_message_id=None,
                                    event="bounced", destination=None, occurred_at=T0,
                                    suppress=("email", "all", "hard_bounce"))])
    assert db.query(CommSuppression).count() == 0
