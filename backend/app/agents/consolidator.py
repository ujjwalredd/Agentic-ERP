"""The Consolidator: detect an intercompany transaction and stage the matched
pair of entries on both entities, using intercompany GL accounts so the
Reporter's consolidation can eliminate them.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import account_id, propose
from app.db.models import Entity, ProposedAction
from app.llm.client import complete_json

AGENT = "Consolidator"
SYSTEM = (
    "You handle multi-entity intercompany transactions. Confirm whether this bank "
    "line is genuinely an intercompany flow between group entities that must be "
    "eliminated on consolidation. If the counterparty entity is not clearly one of "
    "the group's entities, set is_intercompany=false and confidence below 0.5 so a "
    "human decides. Do not assume an intercompany relationship that isn't evidenced."
)


def _counterparty(db: Session, payer_id: int, description: str) -> Entity | None:
    others = list(db.scalars(select(Entity).where(Entity.id != payer_id)))
    for e in others:
        if e.name.lower() in description.lower():
            return e
    # fallback: a sibling entity (same parent)
    payer = db.get(Entity, payer_id)
    for e in others:
        if payer and e.parent_id == payer.parent_id and e.id != payer_id:
            return e
    return others[0] if others else None


def _mock(_user: str) -> dict:
    return {"is_intercompany": True, "confidence": 0.91}


def run(db: Session, data: dict) -> list[ProposedAction]:
    payer_id = data["entity_id"]
    desc = data["description"]
    amount = abs(float(data["amount"]))

    complete_json(
        "consolidator",
        SYSTEM,
        f"Bank line on entity {payer_id}: '{desc}', amount {amount:.2f}. "
        "Return JSON {is_intercompany, confidence}.",
        mock=_mock,
    )

    payee = _counterparty(db, payer_id, desc)
    actions: list[ProposedAction] = []

    # Payer: Dr Intercompany Expense (5300) / Cr Cash (1000)
    payer_lines = [
        {"account_id": account_id(db, payer_id, "5300"), "debit": amount},
        {"account_id": account_id(db, payer_id, "1000"), "credit": amount},
    ]
    actions.append(
        propose(
            db,
            agent=AGENT,
            action_type="eliminate_intercompany",
            summary=f"Book intercompany expense {amount:.2f} on payer (entity {payer_id})",
            confidence=0.91,
            payload={
                "agent": AGENT,
                "entity_id": payer_id,
                "memo": f"Intercompany: {desc}",
                "lines": payer_lines,
                "bank_transaction_id": data.get("bank_transaction_id"),
                "source_event_id": data.get("source_event_id"),
            },
            source_event_id=data.get("source_event_id"),
        )
    )

    # Payee: Dr Cash (1000) / Cr Intercompany Revenue (4100)
    if payee:
        payee_lines = [
            {"account_id": account_id(db, payee.id, "1000"), "debit": amount},
            {"account_id": account_id(db, payee.id, "4100"), "credit": amount},
        ]
        actions.append(
            propose(
                db,
                agent=AGENT,
                action_type="eliminate_intercompany",
                summary=f"Book intercompany revenue {amount:.2f} on payee {payee.name}",
                confidence=0.91,
                payload={
                    "agent": AGENT,
                    "entity_id": payee.id,
                    "memo": f"Intercompany: {desc}",
                    "lines": payee_lines,
                    "source_event_id": data.get("source_event_id"),
                },
                source_event_id=data.get("source_event_id"),
            )
        )
    return actions
