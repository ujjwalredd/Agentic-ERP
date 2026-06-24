"""HITL gate: apply a ProposedAction's mutation only on human approval.

Every approve/reject writes an immutable AuditLog row. Approving a ledger action
posts the entry in one DB transaction, then emits `entry.posted` to trigger
continuous consolidation.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    BankTransaction,
    Bill,
    Correction,
    Invoice,
    JournalEntry,
    ProposedAction,
    AuditLog,
)
from app.config import settings
from app.events import bus
from app.events.types import Event, ENTRY_POSTED
from app.services import ledger, rules, vectors


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
    # Idempotency: never book a bank line that a prior approval already matched
    # (blocks a stale duplicate draft from double-posting the same transaction).
    if payload.get("bank_transaction_id"):
        bt = db.get(BankTransaction, payload["bank_transaction_id"])
        if bt and bt.status == "matched":
            raise ApprovalError("bank line already booked")
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


def auto_approve_if_eligible(db: Session, action: ProposedAction) -> AuditLog | None:
    """Gated autonomy: finalize a draft without a human click only when it came
    from an `auto_approve` Rule and clears the confidence floor. Still posts through
    the normal approve() path — fully audited (actor `system:rule:<id>`) and
    reversible. Returns the AuditLog if auto-approved, else None."""
    if not settings.auto_approve_enabled:
        return None
    payload = action.payload or {}
    rule_id = payload.get("rule_id")
    if not (payload.get("auto_approve") and rule_id):
        return None
    if float(action.confidence) < settings.auto_approve_min_confidence:
        return None
    return approve(db, action, f"system:rule:{rule_id}")


def reject(db: Session, action: ProposedAction, user_id: str, reason: str = "") -> AuditLog:
    if action.status != "pending":
        raise ApprovalError(f"action already {action.status}")
    action.status = "rejected"
    # The reject reason is a learning signal — record it as a Correction.
    if reason:
        db.add(
            Correction(
                proposed_action_id=action.id,
                user_id=user_id,
                kind="reject",
                reason=reason,
                before=action.payload,
                after={},
            )
        )
    audit = AuditLog(
        user_id=user_id,
        agent=action.agent,
        action="rejected",
        proposed_action_id=action.id,
        before={"status": "pending"},
        after={"status": "rejected", "reason": reason},
    )
    db.add(audit)
    db.commit()
    return audit


def apply_edit(
    db: Session,
    action: ProposedAction,
    user_id: str,
    *,
    account_code: str | None,
    reason: str,
    create_rule: bool,
    auto_approve: bool,
) -> AuditLog:
    """Human corrects a draft, then approves it. Records a Correction (the richest
    learning signal), optionally codifies the correction as a Rule, and posts."""
    if action.status != "pending":
        raise ApprovalError(f"action already {action.status}")

    before = dict(action.payload)
    payload = dict(action.payload)
    entity_id = payload.get("entity_id")

    # Re-point the GL (non-cash) line to the corrected account.
    if account_code:
        new_gl = db.scalar(
            select(Account).where(
                Account.entity_id == entity_id, Account.code == account_code
            )
        )
        if new_gl is None:
            raise ApprovalError(f"account {account_code} not found for entity {entity_id}")
        for line in payload.get("lines", []):
            acct = db.get(Account, line["account_id"])
            if acct and acct.code != "1000":  # the GL/expense side, not cash
                line["account_id"] = new_gl.id
        payload["memo"] = f"{payload.get('description', '')} -> {new_gl.name}".strip()
        if payload.get("memory"):
            payload["memory"]["meta"] = {
                "account_code": new_gl.code,
                "account_name": new_gl.name,
            }
        payload["rule_id"] = None  # a human correction overrides any rule provenance
        payload["auto_approve"] = False

    after = dict(payload)
    after["account_code"] = account_code
    db.add(
        Correction(
            proposed_action_id=action.id,
            user_id=user_id,
            kind="edit",
            reason=reason,
            before=before,
            after=after,
        )
    )

    # Optionally codify the correction as a reusable rule.
    if create_rule and account_code and payload.get("description"):
        rules.upsert(
            db,
            entity_id=entity_id,
            pattern=str(payload["description"]).split()[0],
            account_code=account_code,
            auto_approve=auto_approve,
            source="correction",
            created_by=user_id,
        )

    action.payload = payload
    db.flush()
    return approve(db, action, user_id)
