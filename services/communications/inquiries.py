"""
Website inquiries (the public contact form): triage and email replies from the hub.

Replies go through the outbox, so they are retried, tracked and shown in the delivery log; each reply records
the message it was sent as.
"""
import html
from typing import Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models.communications import CommMessage
from models.contact_message import ContactMessage, ContactMessageReply
from models.users import User

from .common import CommError, as_uuid, audit, iso, page_bounds, paged
from .outbox import queue_email

INQUIRY_STATUSES = ("unread", "read", "replied", "resolved")


class InquiryService:
    def __init__(self, db: Session):
        self.db = db

    def _load(self, inquiry_id) -> ContactMessage:
        inquiry = self.db.get(ContactMessage, as_uuid(inquiry_id))
        if not inquiry:
            raise CommError("Inquiry not found", 404)
        return inquiry

    @staticmethod
    def _row(m: ContactMessage, replies: int = 0) -> dict:
        return {
            "id": str(m.id), "first_name": m.first_name, "last_name": m.last_name, "email": m.email,
            "topic": m.topic, "message": m.message, "status": m.status or "unread", "replies": replies,
            "created_at": iso(m.created_at), "updated_at": iso(m.updated_at),
        }

    def list(self, page: int = 1, limit: int = 25, status: Optional[str] = None, q: Optional[str] = None) -> dict:
        page, limit, offset = page_bounds(page, limit)
        query = self.db.query(ContactMessage)
        if status:
            if status not in INQUIRY_STATUSES:
                raise CommError(f"status must be one of {', '.join(INQUIRY_STATUSES)}")
            query = query.filter(ContactMessage.status == status)
        if q:
            like = f"%{q.strip()}%"
            query = query.filter(or_(ContactMessage.email.ilike(like), ContactMessage.first_name.ilike(like),
                                     ContactMessage.last_name.ilike(like), ContactMessage.topic.ilike(like),
                                     ContactMessage.message.ilike(like)))
        total = query.count()
        rows = query.order_by(ContactMessage.created_at.desc()).offset(offset).limit(limit).all()
        counts = dict(self.db.query(ContactMessageReply.contact_message_id, func.count())
                      .filter(ContactMessageReply.contact_message_id.in_([m.id for m in rows]))
                      .group_by(ContactMessageReply.contact_message_id).all()) if rows else {}
        unread = self.db.query(func.count(ContactMessage.id)).filter(ContactMessage.status == "unread").scalar() or 0
        return {**paged([self._row(m, counts.get(m.id, 0)) for m in rows], total, page, limit), "unread": unread}

    def get(self, inquiry_id) -> dict:
        inquiry = self._load(inquiry_id)
        replies = (self.db.query(ContactMessageReply, User, CommMessage)
                   .outerjoin(User, ContactMessageReply.author_id == User.user_id)
                   .outerjoin(CommMessage, ContactMessageReply.comm_message_id == CommMessage.message_id)
                   .filter(ContactMessageReply.contact_message_id == inquiry.id)
                   .order_by(ContactMessageReply.created_at).all())
        return {**self._row(inquiry, len(replies)), "thread": [{
            "id": str(r.reply_id), "body": r.body, "created_at": iso(r.created_at),
            "author": f"{u.first_name} {u.last_name}".strip() if u else "Former staff member",
            "delivery_status": m.status if m else None, "message_id": str(m.message_id) if m else None,
        } for r, u, m in replies]}

    def set_status(self, inquiry_id, status: str, actor_id) -> dict:
        if status not in INQUIRY_STATUSES:
            raise CommError(f"status must be one of {', '.join(INQUIRY_STATUSES)}")
        inquiry = self._load(inquiry_id)
        inquiry.status = status
        audit(self.db, actor_id, "INQUIRY_STATUS_CHANGED", "CONTACT_MESSAGE", inquiry.id, {"status": status})
        self.db.commit()
        return self.get(inquiry.id)

    def reply(self, inquiry_id, body: str, actor_id, resolve: bool = False) -> dict:
        """Emails a reply to the person who wrote in, quoting their message, and records it on the thread."""
        body = (body or "").strip()
        if not body:
            raise CommError("Write a reply first")
        if len(body) > 10_000:
            raise CommError("Reply is too long (10,000 characters at most)")
        inquiry = self._load(inquiry_id)
        author = self.db.get(User, as_uuid(actor_id)) if actor_id else None
        signature = f"{author.first_name} {author.last_name}".strip() if author else "KapuLetu Support"

        def para(text: str) -> str:
            return html.escape(text).replace("\n", "<br>")

        email_html = (
            f"<p>Hello {html.escape(inquiry.first_name)},</p>"
            f"<p>{para(body)}</p>"
            f"<p>Best regards,<br>{html.escape(signature)}<br>KapuLetu Support</p>"
            f'<hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0">'
            f'<p style="font-size:13px;color:#718096">You wrote about “{html.escape(inquiry.topic)}”:</p>'
            f'<blockquote style="font-size:13px;color:#718096;margin:0;padding-left:12px;'
            f'border-left:3px solid #e2e8f0">{para(inquiry.message)}</blockquote>'
        )
        message = queue_email(self.db, inquiry.email, f"Re: {inquiry.topic}", email_html, kind="inquiry_reply")
        self.db.add(ContactMessageReply(contact_message_id=inquiry.id, author_id=as_uuid(actor_id), body=body,
                                        comm_message_id=message.message_id))
        inquiry.status = "resolved" if resolve else "replied"
        audit(self.db, actor_id, "INQUIRY_REPLIED", "CONTACT_MESSAGE", inquiry.id,
              {"message_id": str(message.message_id), "resolved": resolve})
        self.db.commit()
        return self.get(inquiry.id)
