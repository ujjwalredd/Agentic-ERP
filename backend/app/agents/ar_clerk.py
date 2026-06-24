"""The AR Clerk: draft a collections reminder for an overdue invoice."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.base import propose
from app.db.models import ProposedAction
from app.llm.client import complete_json

AGENT = "AR Clerk"
SYSTEM = (
    "You handle accounts receivable collections. Draft a polite, professional payment "
    "reminder for an overdue invoice. Reference ONLY the customer, amount, and due "
    "date provided — do not invent invoice numbers, threats, legal language, fees, or "
    "payment links. The draft is reviewed and sent by a human; you do not send email."
)


def _mock(user: str) -> dict:
    return {
        "subject": "Friendly reminder: invoice past due",
        "body": "Hi, our records show the invoice referenced is past its due date. "
        "Please arrange payment at your earliest convenience. Thank you.",
        "confidence": 0.9,
    }


def run(db: Session, data: dict) -> ProposedAction | None:
    customer = data["customer"]
    amount = float(data["amount"])
    due = data.get("due_date")

    decision = complete_json(
        "ar_clerk",
        SYSTEM,
        f"Customer: {customer}, amount {amount:.2f}, due {due} (overdue). "
        "Return JSON {subject, body, confidence}.",
        mock=_mock,
    )
    payload = {
        "agent": AGENT,
        "invoice_id": data.get("invoice_id"),
        "email": {"subject": decision.get("subject"), "body": decision.get("body")},
        "source_event_id": data.get("source_event_id"),
    }
    return propose(
        db,
        agent=AGENT,
        action_type="send_reminder",
        summary=f"Send overdue reminder to {customer} for {amount:.2f}",
        confidence=decision.get("confidence", 0.9),
        payload=payload,
        source_event_id=data.get("source_event_id"),
    )
