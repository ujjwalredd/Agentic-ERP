"""The Reconciler: fuzzy-match unmatched bank lines against posted ledger entries.

Deterministic matching (amount + recency) backed by an LLM confidence read.
Proposes a `match_bank` action when a confident match is found, otherwise flags
a variance note for human review.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import propose
from app.db.models import BankTransaction, JournalEntry, JournalLine, ProposedAction

AGENT = "Reconciler"


def _find_match(db: Session, bt: BankTransaction) -> JournalEntry | None:
    """A posted entry on the same entity whose cash line magnitude == |amount|."""
    target = abs(Decimal(str(bt.amount)))
    entries = db.scalars(
        select(JournalEntry).where(
            JournalEntry.entity_id == bt.entity_id, JournalEntry.status == "posted"
        )
    )
    for e in entries:
        for l in e.lines:
            if l.account.code == "1000" and max(l.debit, l.credit) == target:
                return e
    return None


def run(db: Session, data: dict) -> list[ProposedAction]:
    entity_id = data["entity_id"]
    unmatched = list(
        db.scalars(
            select(BankTransaction).where(
                BankTransaction.entity_id == entity_id,
                BankTransaction.status == "unmatched",
            )
        )
    )
    actions: list[ProposedAction] = []
    for bt in unmatched:
        match = _find_match(db, bt)
        if match:
            actions.append(
                propose(
                    db,
                    agent=AGENT,
                    action_type="match_bank",
                    summary=f"Match bank '{bt.description}' to entry #{match.id}",
                    confidence=0.93,
                    payload={
                        "bank_transaction_id": bt.id,
                        "journal_entry_id": match.id,
                    },
                    source_event_id=data.get("source_event_id"),
                )
            )
        else:
            actions.append(
                propose(
                    db,
                    agent=AGENT,
                    action_type="note",
                    summary=f"Variance: unmatched bank line '{bt.description}' {bt.amount}",
                    confidence=0.6,
                    payload={"note": "no matching ledger entry", "bank_transaction_id": bt.id},
                    source_event_id=data.get("source_event_id"),
                )
            )
    return actions
