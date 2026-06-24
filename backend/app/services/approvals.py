"""HITL gate: apply a ProposedAction's mutation only on human approval.

Every approve/reject writes an immutable AuditLog row. Approving a ledger action
posts the entry in one DB transaction, then emits `entry.posted` to trigger
continuous consolidation.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    BankTransaction,
    Bill,
    Invoice,
    JournalEntry,
    ProposedAction,
    AuditLog,
)
from app.events import bus
from app.events.types import Event, ENTRY_POSTED
from app.services import ledger, vectors


class ApprovalError(RuntimeError):
    pass


def _validate_accounts(db: Session, entity_id: int, lines: list[dict]) -> None:
    """Every line must reference a real account that belongs to this entity.
    Stops a hallucinated/tampered payload from posting cross-entity or to a bogus
    account, regardless of what any agent proposed."""
    for l in lines:
        acct = db.get(Account, l.get("account_id"))
        if acct is None:
            raise ApprovalError(f"account {l.get('account_id')} does not exist")
        if acct.entity_id != entity_id:
            raise ApprovalError(
                f"account {acct.id} belongs to entity {acct.entity_id}, not {entity_id}"
            )


def _apply_book_journal_entry(db: Session, payload: dict) -> dict:
    """payload: {entity_id, memo, date?, lines[], agent, bank_transaction_id?, memory?}"""
    _validate_accounts(db, payload["entity_id"], payload["lines"])
    entry = ledger.create_draft_entry(
        db,
        entity_id=payload["entity_id"],
        memo=payload.get("memo", ""),
        lines=payload["lines"],
        created_by_agent=payload.get("agent", "system"),
        source_event_id=payload.get("source_event_id"),
        date=payload.get("date"),
    )
    ledger.post_entry(db, entry)

    # Optionally close the originating bank line.
    if payload.get("bank_transaction_id"):
        bt = db.get(BankTransaction, payload["bank_transaction_id"])
        if bt:
            bt.status = "matched"
            bt.matched_journal_entry_id = entry.id

    # Categorizer learns: persist the approved categorization to vector memory.
    mem = payload.get("memory")
    if mem:
        vectors.add_doc(db, text=mem["text"], meta=mem.get("meta", {}))

    return {"journal_entry_id": entry.id, "status": "posted"}


def _apply_match_bank(db: Session, payload: dict) -> dict:
    """payload: {bank_transaction_id, journal_entry_id}"""
    bt = db.get(BankTransaction, payload["bank_transaction_id"])
    if not bt:
        raise ApprovalError("bank transaction not found")
    bt.status = "matched"
    bt.matched_journal_entry_id = payload.get("journal_entry_id")
    return {"bank_transaction_id": bt.id, "status": "matched"}


def _apply_stage_payable(db: Session, payload: dict) -> dict:
    """payload: {bill_id} -> mark a staged bill ready; book AP via lines if provided."""
    if payload.get("lines"):
        return _apply_book_journal_entry(db, payload)
    bill = db.get(Bill, payload["bill_id"])
    if bill:
        bill.status = "approved"
    return {"bill_id": payload.get("bill_id"), "status": "approved"}


def _apply_send_reminder(db: Session, payload: dict) -> dict:
    """payload: {invoice_id, email}. No ledger mutation; records the send."""
    inv = db.get(Invoice, payload.get("invoice_id"))
    if inv:
        inv.status = "reminded"
    return {"invoice_id": payload.get("invoice_id"), "status": "reminder_sent"}


def _apply_note(db: Session, payload: dict) -> dict:
    """Informational action (Reporter/Closer/variance). Acknowledged, no mutation."""
    return {"status": "acknowledged"}


# action_type -> handler
_HANDLERS = {
    "book_journal_entry": _apply_book_journal_entry,
    "match_bank": _apply_match_bank,
    "stage_payable": _apply_stage_payable,
    "eliminate_intercompany": _apply_book_journal_entry,
    "send_reminder": _apply_send_reminder,
    "note": _apply_note,
}


def approve(db: Session, action: ProposedAction, user_id: str) -> AuditLog:
    if action.status != "pending":
        raise ApprovalError(f"action already {action.status}")

    handler = _HANDLERS.get(action.action_type)
    if handler is None:
        raise ApprovalError(f"no handler for action_type {action.action_type}")

    before = {"status": action.status}
    after = handler(db, action.payload)
    action.status = "approved"

    audit = AuditLog(
        user_id=user_id,
        agent=action.agent,
        action="approved",
        proposed_action_id=action.id,
        before=before,
        after=after,
    )
    db.add(audit)
    db.commit()

    # Continuous consolidation: notify on any posted ledger change.
    if "journal_entry_id" in after:
        bus.publish(
            Event(
                type=ENTRY_POSTED,
                data={
                    "journal_entry_id": after["journal_entry_id"],
                    "proposed_action_id": action.id,
                },
            )
        )
    return audit


def reject(db: Session, action: ProposedAction, user_id: str) -> AuditLog:
    if action.status != "pending":
        raise ApprovalError(f"action already {action.status}")
    action.status = "rejected"
    audit = AuditLog(
        user_id=user_id,
        agent=action.agent,
        action="rejected",
        proposed_action_id=action.id,
        before={"status": "pending"},
        after={"status": "rejected"},
    )
    db.add(audit)
    db.commit()
    return audit
