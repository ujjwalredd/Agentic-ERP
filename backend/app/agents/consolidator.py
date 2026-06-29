"""The Consolidator: detect an intercompany transaction and stage the matched
pair of entries on both entities, using intercompany GL accounts so the
Reporter's consolidation can eliminate them.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import account_id, pending_exists, propose
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
    # fallback: a single unambiguous sibling entity (same parent)
    payer = db.get(Entity, payer_id)
    siblings = [
        e for e in others
        if payer and e.parent_id == payer.parent_id and e.id != payer_id
    ]
    if len(siblings) == 1:
        return siblings[0]
    # Ambiguous or unidentifiable: do NOT guess an entity to post to.
    return None


def _mock(_user: str) -> dict:
    return {"is_intercompany": True, "confidence": 0.91}


def _note(db: Session, entity_id: int, summary: str, note: str, data: dict) -> ProposedAction:
    """Escalate to a human instead of auto-staging a (possibly wrong) elimination."""
    return propose(
        db,
        agent=AGENT,
        action_type="note",
        summary=summary,
        confidence=0.4,
        payload={
            "note": note,
            "entity_id": entity_id,
            "bank_transaction_id": data.get("bank_transaction_id"),
            "source_event_id": data.get("source_event_id"),
        },
        source_event_id=data.get("source_event_id"),
    )


def run(db: Session, data: dict) -> list[ProposedAction]:
    payer_id = data["entity_id"]
    desc = data["description"]
    amount = abs(float(data["amount"]))

    # Idempotency: a re-fired event must not stage a second elimination pair.
    bt_id = data.get("bank_transaction_id")
    if bt_id and pending_exists(
        db, "bank_transaction_id", bt_id, action_type="eliminate_intercompany"
    ):
        return []

    decision = complete_json(
        "consolidator",
        SYSTEM,
        f"Bank line on entity {payer_id}: '{desc}', amount {amount:.2f}. "
        "Return JSON {is_intercompany, confidence}.",
        mock=_mock,
    )
    confidence = float(decision.get("confidence", 0.5))

    # SAFETY GATE: respect the model's own judgement. If it is not confident this
    # is a genuine intercompany flow, escalate to a human rather than auto-staging
    # two ledger entries on two entities.
    if not decision.get("is_intercompany"):
        return [
            _note(
                db,
                payer_id,
                f"Possible intercompany '{desc}' needs human confirmation",
                "Model did not confirm an intercompany relationship; not auto-eliminated.",
                data,
            )
        ]

    # Required GL accounts on the payer; if any is missing, escalate (don't post None).
    payer_exp = account_id(db, payer_id, "5300")
    payer_cash = account_id(db, payer_id, "1000")
    if payer_exp is None or payer_cash is None:
        return [
            _note(
                db,
                payer_id,
                f"Intercompany '{desc}' — payer missing intercompany accounts",
                "Payer entity lacks 5300/1000; cannot stage elimination.",
                data,
            )
        ]

    actions: list[ProposedAction] = []

    # Payer: Dr Intercompany Expense (5300) / Cr Cash (1000)
    actions.append(
        propose(
            db,
            agent=AGENT,
            action_type="eliminate_intercompany",
            summary=f"Book intercompany expense {amount:.2f} on payer (entity {payer_id})",
            confidence=confidence,
            payload={
                "agent": AGENT,
                "entity_id": payer_id,
                "memo": f"Intercompany: {desc}",
                "lines": [
                    {"account_id": payer_exp, "debit": amount},
                    {"account_id": payer_cash, "credit": amount},
                ],
                "bank_transaction_id": bt_id,
                "source_event_id": data.get("source_event_id"),
            },
            source_event_id=data.get("source_event_id"),
        )
    )

    # Payee: Dr Cash (1000) / Cr Intercompany Revenue (4100). Only stage if we can
    # identify the counterparty AND it has the required accounts — otherwise note.
    payee = _counterparty(db, payer_id, desc)
    payee_cash = account_id(db, payee.id, "1000") if payee else None
    payee_rev = account_id(db, payee.id, "4100") if payee else None
    if payee and payee_cash is not None and payee_rev is not None:
        actions.append(
            propose(
                db,
                agent=AGENT,
                action_type="eliminate_intercompany",
                summary=f"Book intercompany revenue {amount:.2f} on payee {payee.name}",
                confidence=confidence,
                payload={
                    "agent": AGENT,
                    "entity_id": payee.id,
                    "memo": f"Intercompany: {desc}",
                    "lines": [
                        {"account_id": payee_cash, "debit": amount},
                        {"account_id": payee_rev, "credit": amount},
                    ],
                    "source_event_id": data.get("source_event_id"),
                },
                source_event_id=data.get("source_event_id"),
            )
        )
    else:
        actions.append(
            _note(
                db,
                payer_id,
                f"Intercompany '{desc}' — counterparty unresolved",
                "Could not identify a group counterparty for the payee leg; "
                "payer leg staged, payee leg needs human routing.",
                data,
            )
        )
    return actions
