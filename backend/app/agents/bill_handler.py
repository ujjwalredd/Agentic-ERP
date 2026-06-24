"""The Bill Handler: extract a vendor bill's line items and stage a payable."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.base import account_id, propose
from app.db.models import ProposedAction
from app.llm.client import complete_json

AGENT = "Bill Handler"
SYSTEM = (
    "You process a vendor invoice for accounts payable. Extract ONLY the expense "
    "category and total that are present in the input — never infer an amount that "
    "is not given. Map to a standard GL expense account code (5000-series). If the "
    "vendor or amount is unclear, set confidence below 0.5 for human review. You are "
    "staging a draft payable; you are not paying anyone."
)


def _mock(_user: str) -> dict:
    return {"account_code": "5000", "account_name": "Software Subscriptions", "confidence": 0.88}


def run(db: Session, data: dict) -> ProposedAction | None:
    entity_id = data["entity_id"]
    vendor = data["vendor"]
    amount = float(data["amount"])

    decision = complete_json(
        "bill_handler",
        SYSTEM,
        f"Vendor: {vendor}, amount {amount:.2f}, lines: {data.get('lines')}. "
        "Return JSON {account_code, account_name, confidence}.",
        mock=_mock,
    )
    code = decision.get("account_code", "5000")
    gl_id = account_id(db, entity_id, code) or account_id(db, entity_id, "5000")
    ap_id = account_id(db, entity_id, "2000")

    # Dr expense / Cr accounts payable -> stages the payable.
    lines = [
        {"account_id": gl_id, "debit": amount},
        {"account_id": ap_id, "credit": amount},
    ]
    payload = {
        "agent": AGENT,
        "entity_id": entity_id,
        "memo": f"Bill from {vendor}",
        "lines": lines,
        "bill_id": data.get("bill_id"),
        "source_event_id": data.get("source_event_id"),
    }
    return propose(
        db,
        agent=AGENT,
        action_type="stage_payable",
        summary=f"Stage payable {amount:.2f} to {vendor} ({code})",
        confidence=decision.get("confidence", 0.85),
        payload=payload,
        source_event_id=data.get("source_event_id"),
    )
