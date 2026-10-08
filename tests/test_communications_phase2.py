"""
Communications phase 2: drafts, submitting and pulling back, duplicating, test sends, and checking WhatsApp
broadcasts against the approved-template catalogue from Meta.
"""
import pytest
from test_communications_phase1 import (  # noqa: F401  (Session is a fixture)
    FakeEmail,
    FakeWhatsApp,
    Session,
    dispatcher,
    email_broadcast,
    person,
)

from models.communications import CommBroadcast, CommMessage
from models.notification import Notification
from models.system_config import SystemConfig
from services.communications import broadcasts as broadcasts_module
from services.communications.broadcasts import BroadcastService
from services.communications.common import CommError
from services.communications.providers import whatsapp as wa_module
from services.communications.providers.whatsapp import describe_template

# --- drafts ---

def test_draft_is_saved_incomplete_and_validated_on_submit(db):
    author, submitter = person(db, "Author", role="content_manager"), person(db, "Sub", role="admin")
    svc = BroadcastService(db)
    draft = svc.save_draft({"title": "Half done", "channels": ["email"],
                            "content": {"email": {"subject": "Hi", "html": ""}}}, author.user_id)
    assert draft["status"] == "draft"
    assert dispatcher(db).run_once()["broadcasts_started"] == 0  # drafts never go out

    with pytest.raises(CommError, match="Email needs a subject and a body"):
        svc.submit(draft["id"], submitter.user_id)
    assert svc.get(draft["id"])["status"] == "draft"  # a failed submit leaves the draft alone

    svc.save_draft({**email_broadcast(), "title": "Done"}, author.user_id, draft["id"])
    out = svc.submit(draft["id"], submitter.user_id)
    assert out["status"] == "queued" and out["title"] == "Done"
    assert out["created_by"] == "Sub Test"  # the approval rule is checked against whoever submitted

    with pytest.raises(CommError, match="Only drafts can be changed"):
        svc.save_draft({"title": "Too late"}, author.user_id, draft["id"])
    with pytest.raises(CommError, match="Only drafts can be changed"):
        svc.delete_draft(draft["id"], author.user_id)


def test_delete_draft(db):
    svc = BroadcastService(db)
    draft = svc.save_draft({"title": "Scratch"}, None)
    svc.delete_draft(draft["id"], None)
    assert db.query(CommBroadcast).count() == 0


def test_returning_to_draft_voids_approval(db):
    author, approver = person(db, "Author"), person(db, "Approver", role="admin")
    for _ in range(3):
        person(db)
    db.add(SystemConfig(config_key="comm_marketing_approval_threshold", config_value=2))
    db.commit()
    svc = BroadcastService(db)

    created = svc.create(email_broadcast("marketing", scheduled_for="2099-01-01T08:00:00Z"), author.user_id)
    svc.approve(created["id"], approver.user_id)
    pulled = svc.return_to_draft(created["id"], author.user_id)
    assert pulled["status"] == "draft" and pulled["approved_by"] is None
    assert svc.submit(created["id"], author.user_id)["status"] == "awaiting_approval"  # needs approving again


def test_cannot_return_to_draft_once_sending(db):
    person(db)
    svc = BroadcastService(db)
    created = svc.create(email_broadcast(), None)
    dispatcher(db).start_due_broadcasts()
    with pytest.raises(CommError, match="haven't started"):
        svc.return_to_draft(created["id"], None)


def test_duplicate_makes_an_editable_copy(db):
    person(db)
    svc = BroadcastService(db)
    source = svc.create(email_broadcast("marketing", channels=["email", "in_app"]), None)
    dispatcher(db).run_once()

    copy = svc.duplicate(source["id"], None)
    assert copy["status"] == "draft" and copy["title"] == "Copy of October update"
    assert copy["content"]["email"] == source["content"]["email"] and copy["category"] == "marketing"
    assert copy["recipients_count"] == 0 and copy["stats"]["channels"] == {}

    legacy = CommBroadcast(title="Old", category="service", status="completed", audience={"type": "legacy", "label": "all_members"},
                           channels=["email"], content={"email": {"subject": "x", "html": "<p>x</p>"}}, stats={})
    db.add(legacy)
    db.commit()
    assert svc.duplicate(legacy.broadcast_id, None)["audience"] == {"type": "customers"}


# --- test sends ---

def test_test_send_goes_only_to_the_tester(db):
    me = person(db, "Tess", phone="+254 700 111 222")
    person(db, "Customer")
    email, wa = FakeEmail(), FakeWhatsApp()
    svc = BroadcastService(db, email_provider=email, whatsapp_provider=wa)
    data = email_broadcast("marketing", channels=["email", "in_app", "whatsapp"])

    out = svc.test_send(data, me.user_id)["results"]
    assert all(r["ok"] for r in out.values())
    [[envelope]] = email.batches
    assert envelope.to == me.email and envelope.subject == "[Test] Hi Tess"
    assert "/unsubscribe?token=" in envelope.html  # marketing tests show the real footer
    assert wa.sent == [("254700111222", "october_update", "en", ["Tess"])]
    assert db.query(Notification).filter_by(user_id=me.user_id, type="admin_broadcast_test").count() == 1
    assert db.query(CommBroadcast).count() == 0 and db.query(CommMessage).count() == 0


def test_test_send_validates_content(db):
    me = person(db)
    bad = email_broadcast()
    bad["content"]["email"]["subject"] = ""
    with pytest.raises(CommError, match="subject"):
        BroadcastService(db, email_provider=FakeEmail()).test_send(bad, me.user_id)


# --- WhatsApp template catalogue ---

def test_describe_template():
    simple = describe_template({"name": "promo", "language": "en", "category": "MARKETING", "components": [
        {"type": "HEADER", "format": "TEXT", "text": "October news"},
        {"type": "BODY", "text": "Hi {{1}}, your plan {{2}} renews on {{3}}."},
        {"type": "BUTTONS", "buttons": [{"type": "URL", "url": "https://kapuletu.co.ke/pricing"}]},
    ]})
    assert (simple["variables"], simple["sendable"], simple["category"]) == (3, True, "marketing")

    media = describe_template({"name": "m", "language": "en", "components": [
        {"type": "HEADER", "format": "IMAGE"}, {"type": "BODY", "text": "Hi"}]})
    assert not media["sendable"] and media["unsupported_reason"] == "has a media header"

    named = describe_template({"name": "n", "language": "en", "components": [{"type": "BODY", "text": "Hi {{name}}"}]})
    assert not named["sendable"] and "named variables" in named["unsupported_reason"]

    link = describe_template({"name": "l", "language": "en", "components": [
        {"type": "BODY", "text": "Hi"},
        {"type": "BUTTONS", "buttons": [{"type": "URL", "url": "https://x.ke/{{1}}"}]}]})
    assert link["unsupported_reason"] == "has a dynamic button link"


def test_whatsapp_broadcast_checked_against_catalogue(db, monkeypatch):
    person(db)
    catalogue = [describe_template({"name": "october_update", "language": "en", "components": [
        {"type": "BODY", "text": "Hi {{1}}, see what's new."}]})]
    monkeypatch.setattr(broadcasts_module, "approved_templates", lambda force=False: catalogue)
    svc = BroadcastService(db)

    unknown = email_broadcast(channels=["whatsapp"])
    unknown["content"]["whatsapp"]["template"] = "made_up"
    with pytest.raises(CommError, match="not an approved WhatsApp template"):
        svc.create(unknown, None)

    wrong_count = email_broadcast(channels=["whatsapp"])
    wrong_count["content"]["whatsapp"]["params"] = ["{{first_name}}", "extra"]
    with pytest.raises(CommError, match="needs 1 variable"):
        svc.create(wrong_count, None)

    assert svc.create(email_broadcast(channels=["whatsapp"]), None)["status"] == "queued"


def test_catalogue_follows_pages_keeps_approved_and_caches(monkeypatch):
    monkeypatch.setenv("META_WABA_ID", "waba1")
    monkeypatch.setenv("META_ACCESS_TOKEN", "token")
    wa_module._cache.update(at=0.0, templates=None)
    calls = []

    class Response:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self.body

    pages = {
        None: {"data": [{"name": "b_tpl", "language": "en", "status": "APPROVED", "components": []},
                        {"name": "draft_tpl", "language": "en", "status": "PENDING", "components": []}],
               "paging": {"next": "https://graph.facebook.com/next-page"}},
        "https://graph.facebook.com/next-page": {"data": [
            {"name": "a_tpl", "language": "sw", "status": "APPROVED", "components": []}]},
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        return Response(pages[None if "message_templates" in url else url])

    monkeypatch.setattr(wa_module.httpx, "get", fake_get)
    names = [t["name"] for t in wa_module.approved_templates()]
    assert names == ["a_tpl", "b_tpl"] and len(calls) == 2
    wa_module.approved_templates()
    assert len(calls) == 2  # served from cache
    wa_module._cache.update(at=0.0, templates=None)

    monkeypatch.delenv("META_WABA_ID")
    assert wa_module.approved_templates() is None
