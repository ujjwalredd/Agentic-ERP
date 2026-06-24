"""The only module that mutates the posted ledger. Enforces double-entry."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import JournalEntry, JournalLine

CENTS = Decimal("0.01")


class UnbalancedEntryError(ValueError):
    pass


def _validate_balanced(lines: list[dict]) -> None:
    debits = sum(Decimal(str(l.get("debit", 0))) for l in lines)
    credits = sum(Decimal(str(l.get("credit", 0))) for l in lines)
    if debits.quantize(CENTS) != credits.quantize(CENTS):
        raise UnbalancedEntryError(
            f"debits {debits} != credits {credits}"
        )
    if debits == 0:
        raise UnbalancedEntryError("entry has zero total")


def create_draft_entry(
    db: Session,
    entity_id: int,
    memo: str,
    lines: list[dict],
    created_by_agent: str = "system",
    source_event_id: str | None = None,
    date=None,
) -> JournalEntry:
    """Build a *draft* journal entry. Validates balance but does not post.

    `lines`: [{"account_id": int, "debit": x} | {"account_id": int, "credit": y}]
    """
    _validate_balanced(lines)
    entry = JournalEntry(
        entity_id=entity_id,
        memo=memo,
        status="draft",
        created_by_agent=created_by_agent,
        source_event_id=source_event_id,
    )
    if date is not None:
        entry.date = date
    db.add(entry)
    db.flush()
    for l in lines:
        db.add(
            JournalLine(
                journal_entry_id=entry.id,
                account_id=l["account_id"],
                debit=Decimal(str(l.get("debit", 0))),
                credit=Decimal(str(l.get("credit", 0))),
            )
        )
    db.flush()
    return entry


def post_entry(db: Session, entry: JournalEntry) -> JournalEntry:
    """Flip a draft entry to posted after re-validating balance."""
    lines = [
        {"debit": l.debit, "credit": l.credit} for l in entry.lines
    ]
    _validate_balanced(lines)
    entry.status = "posted"
    db.flush()
    return entry
