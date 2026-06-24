"""The Closer: runs the month-end close. Surfaces anomalies and fans out to the
Reconciler (tie out the bank feed) and the Reporter (consolidated narrative).
This is the path that exercises the deterministic-plus-narrative agents at close.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import reconciler, reporter
from app.agents.base import propose
from app.db.models import BankTransaction, ProposedAction
from app.llm.client import complete_json

AGENT = "Closer"
SYSTEM = (
    "You run an accounting month-end close. From the checklist state provided, surface "
    "the single most important real anomaly or risk for the controller. Report only "
    "what the data shows (e.g. unreconciled lines) — do not invent figures, fraud "
    "claims, or issues that are not evidenced. If nothing is wrong, say so plainly."
)


def _mock(_user: str, unmatched: int) -> dict:
    if unmatched:
        return {
            "anomaly": f"{unmatched} bank line(s) still unreconciled at close.",
            "confidence": 0.7,
        }
    return {"anomaly": "No blocking anomalies; books appear tied out.", "confidence": 0.85}


def run(db: Session, data: dict) -> list[ProposedAction]:
    entity_id = data["entity_id"]
    unmatched = db.scalar(
        select(BankTransaction)
        .where(
            BankTransaction.entity_id == entity_id,
            BankTransaction.status == "unmatched",
        )
        .limit(1)
    )
    n_unmatched = len(
        list(
            db.scalars(
                select(BankTransaction).where(
                    BankTransaction.entity_id == entity_id,
                    BankTransaction.status == "unmatched",
                )
            )
        )
    )

    decision = complete_json(
        "closer",
        SYSTEM,
        f"Entity {data.get('entity')} close. Unmatched bank lines: {n_unmatched}. "
        "Return JSON {anomaly, confidence}.",
        mock=lambda _u: _mock(_u, n_unmatched),
    )

    actions: list[ProposedAction] = [
        propose(
            db,
            agent=AGENT,
            action_type="note",
            summary=f"Close review — {data.get('entity', entity_id)}",
            confidence=decision.get("confidence", 0.8),
            payload={"note": decision.get("anomaly"), "entity_id": entity_id},
            source_event_id=data.get("source_event_id"),
        )
    ]

    # Fan out: Reconciler ties out the bank feed; Reporter writes the narrative.
    actions += reconciler.run(db, data)
    rep = reporter.run(db, data)
    if rep:
        actions.append(rep)
    return actions
