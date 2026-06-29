"""The Reconciler: fuzzy-match unmatched bank lines against posted ledger entries.

Deterministic matching (amount + recency) backed by an LLM confidence read.
Proposes a `match_bank` action when a confident match is found, otherwise flags
a variance note for human review.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.base import pending_exists, propose
from app.db.models import BankTransaction, JournalEntry, ProposedAction

AGENT = "Reconciler"


def _candidate_matches(db: Session, bt: BankTransaction) -> list[JournalEntry]:
    """Posted entries on the same entity whose cash-line magnitude == |amount|,
    excluding entries already tied to some other bank line. Returns ALL candidates
    so the caller can detect ambiguity instead of silently taking the first one."""
    target = abs(Decimal(str(bt.amount)))
    # Entries already claimed by another bank line — never re-match these.
    claimed = set(
        db.scalars(
            select(BankTransaction.matched_journal_entry_id).where(
                BankTransaction.matched_journal_entry_id.is_not(None)
            )
        )
    )
    entries = db.scalars(
        select(JournalEntry).where(
            JournalEntry.entity_id == bt.entity_id, JournalEntry.status == "posted"
        )
    )
    out: list[JournalEntry] = []
    for e in entries:
        if e.id in claimed:
            continue
        if any(l.account.code == "1000" and max(l.debit, l.credit) == target for l in e.lines):
            out.append(e)
    return out


def _date_key(bt: BankTransaction):
    return lambda e: abs((e.date - bt.date).days) if e.date and bt.date else 10**9


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
        # Idempotency: skip if a reconciliation draft for this line is already pending
        # (re-firing close must not duplicate match/variance drafts).
        if pending_exists(db, "bank_transaction_id", bt.id, action_type="match_bank") or \
           pending_exists(db, "bank_transaction_id", bt.id, action_type="note"):
            continue

        candidates = _candidate_matches(db, bt)
        if len(candidates) == 1:
            match = candidates[0]
            same_day = match.date == bt.date if match.date and bt.date else False
            actions.append(
                propose(
                    db,
                    agent=AGENT,
                    action_type="match_bank",
                    summary=f"Match bank '{bt.description}' to entry #{match.id}",
                    # Amount+date agreement is a strong tie; amount-only is weaker.
                    confidence=0.93 if same_day else 0.75,
                    payload={
                        "bank_transaction_id": bt.id,
                        "journal_entry_id": match.id,
                    },
                    source_event_id=data.get("source_event_id"),
                )
            )
        elif len(candidates) > 1:
            # Ambiguous: same-amount entries exist. Do NOT auto-tie — flag for a human,
            # surfacing the closest-by-date candidate as a hint.
            best = min(candidates, key=_date_key(bt))
            actions.append(
                propose(
                    db,
                    agent=AGENT,
                    action_type="note",
                    summary=f"Ambiguous match for '{bt.description}' {bt.amount} "
                    f"({len(candidates)} same-amount entries)",
                    confidence=0.5,
                    payload={
                        "note": "multiple posted entries match this amount; human must pick",
                        "bank_transaction_id": bt.id,
                        "candidate_entry_ids": [e.id for e in candidates],
                        "suggested_entry_id": best.id,
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
