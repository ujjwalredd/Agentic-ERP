"""Agent correctness fixes, end to end against a real (seeded) database.

Runs only when Postgres/pgvector is reachable; otherwise skipped (same pattern as
test_approval_flow) so the pure unit suite still runs anywhere. All LLM calls are
mocked (conftest forces USE_MOCK_LLM=true).
"""
import random

import pytest
from sqlalchemy import select

from app.db.base import SessionLocal, engine, init_db
from app.db.models import Account, BankTransaction, Entity, JournalEntry, ProposedAction
from app.agents import consolidator, reconciler
from app.services import approvals, ledger


def _db_available() -> bool:
    try:
        with engine.connect():
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="Postgres not reachable; agent integration tests skipped"
)


@pytest.fixture(scope="module", autouse=True)
def _seeded():
    init_db()
    yield


def _entity(db, name):
    return db.scalar(select(Entity).where(Entity.name == name))


def _fresh_bt(db, entity_id, desc, amount):
    bt = BankTransaction(entity_id=entity_id, amount=amount, description=desc)
    db.add(bt)
    db.commit()
    return bt


# ---- 1.1 Consolidator respects its own is_intercompany gate ------------------
def test_consolidator_escalates_when_not_intercompany(monkeypatch):
    db = SessionLocal()
    try:
        sub_b = _entity(db, "SubB")
        bt = _fresh_bt(db, sub_b.id, f"RANDOM VENDOR {random.random()}", -100)
        monkeypatch.setattr(
            consolidator, "complete_json",
            lambda *a, **k: {"is_intercompany": False, "confidence": 0.3},
        )
        actions = consolidator.run(
            db, {"entity_id": sub_b.id, "description": bt.description,
                 "amount": -100, "bank_transaction_id": bt.id}
        )
        assert actions and all(a.action_type == "note" for a in actions)
    finally:
        db.close()


def test_consolidator_idempotent_on_replay(monkeypatch):
    db = SessionLocal()
    try:
        sub_b = _entity(db, "SubB")
        bt = _fresh_bt(db, sub_b.id, f"INTERCOMPANY {random.random()} - SubA", -2000)
        monkeypatch.setattr(
            consolidator, "complete_json",
            lambda *a, **k: {"is_intercompany": True, "confidence": 0.9},
        )
        data = {"entity_id": sub_b.id, "description": bt.description,
                "amount": -2000, "bank_transaction_id": bt.id}
        first = consolidator.run(db, data)
        assert any(a.action_type == "eliminate_intercompany" for a in first)
        second = consolidator.run(db, data)  # replay
        assert second == []
    finally:
        db.close()


# ---- 1.3 Reconciler flags ambiguity instead of a false match ----------------
def test_reconciler_ambiguous_amount_becomes_note():
    db = SessionLocal()
    try:
        sub_a = _entity(db, "SubA")
        cash = db.scalar(
            select(Account).where(Account.entity_id == sub_a.id, Account.code == "1000")
        )
        exp = db.scalar(
            select(Account).where(Account.entity_id == sub_a.id, Account.code == "5000")
        )
        amt = 77.77
        # two posted entries with the same cash-line magnitude -> ambiguous
        for _ in range(2):
            e = ledger.create_draft_entry(
                db, entity_id=sub_a.id, memo="dup amount",
                lines=[{"account_id": exp.id, "debit": amt},
                       {"account_id": cash.id, "credit": amt}],
            )
            ledger.post_entry(db, e)
        db.commit()
        bt = _fresh_bt(db, sub_a.id, f"AMBIG {random.random()}", -amt)
        actions = reconciler.run(db, {"entity_id": sub_a.id})
        mine = [a for a in actions if a.payload.get("bank_transaction_id") == bt.id]
        assert mine and mine[0].action_type == "note"
        assert "candidate_entry_ids" in mine[0].payload
    finally:
        db.close()


# ---- 1.4 Edit-flow repoint safety -------------------------------------------
def _pending_book_action(db, entity_id, lines, description):
    a = ProposedAction(
        agent="Categorizer", action_type="book_journal_entry",
        summary="t", confidence=0.9,
        payload={"agent": "Categorizer", "entity_id": entity_id, "memo": "",
                 "lines": lines, "description": description},
        status="pending",
    )
    db.add(a)
    db.commit()
    return a


def test_edit_refuses_revenue_entry():
    db = SessionLocal()
    try:
        sub_a = _entity(db, "SubA")
        cash = db.scalar(select(Account).where(Account.entity_id == sub_a.id, Account.code == "1000"))
        rev = db.scalar(select(Account).where(Account.entity_id == sub_a.id, Account.code == "4000"))
        a = _pending_book_action(
            db, sub_a.id,
            [{"account_id": cash.id, "debit": 500}, {"account_id": rev.id, "credit": 500}],
            "STRIPE PAYOUT",
        )
        with pytest.raises(approvals.ApprovalError):
            approvals.apply_edit(
                db, a, "tester", account_code="5100", reason="x",
                create_rule=False, auto_approve=False,
            )
    finally:
        db.close()


def test_edit_succeeds_on_single_expense_entry():
    db = SessionLocal()
    try:
        sub_a = _entity(db, "SubA")
        cash = db.scalar(select(Account).where(Account.entity_id == sub_a.id, Account.code == "1000"))
        exp = db.scalar(select(Account).where(Account.entity_id == sub_a.id, Account.code == "5000"))
        new = db.scalar(select(Account).where(Account.entity_id == sub_a.id, Account.code == "5100"))
        a = _pending_book_action(
            db, sub_a.id,
            [{"account_id": exp.id, "debit": 60}, {"account_id": cash.id, "credit": 60}],
            "STAPLES STORE",
        )
        audit = approvals.apply_edit(
            db, a, "tester", account_code="5100", reason="recategorize",
            create_rule=False, auto_approve=False,
        )
        assert audit.action == "approved"
        # the expense line now points at the corrected account
        je = db.scalar(select(JournalEntry).where(JournalEntry.id == audit.after["journal_entry_id"]))
        assert any(l.account_id == new.id for l in je.lines)
    finally:
        db.close()
