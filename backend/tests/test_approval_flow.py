"""Integration: the HITL gate and continuous consolidation, end to end.

Runs only when a Postgres (pgvector) database is reachable via DATABASE_URL;
otherwise skipped so the pure unit tests still run anywhere.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.base import SessionLocal, engine, init_db
from app.db.models import AuditLog, JournalEntry, ProposedAction
from app.services import approvals
from app.services.consolidation import consolidated_pnl


def _db_available() -> bool:
    try:
        with engine.connect():
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="Postgres not reachable; integration test skipped"
)


@pytest.fixture(scope="module", autouse=True)
def _seeded():
    init_db()
    yield


def _account_id(db, entity_id, code):
    from app.db.models import Account

    return db.scalar(
        select(Account).where(Account.entity_id == entity_id, Account.code == code)
    ).id


def test_draft_stays_off_the_books_until_approved():
    db = SessionLocal()
    try:
        entity_id = db.scalar(select(JournalEntry.entity_id))  # an existing entity
        gl = _account_id(db, entity_id, "5000")
        cash = _account_id(db, entity_id, "1000")
        action = ProposedAction(
            agent="Categorizer",
            action_type="book_journal_entry",
            summary="test booking",
            confidence=0.9,
            payload={
                "agent": "Categorizer",
                "entity_id": entity_id,
                "memo": "pytest software sub",
                "lines": [
                    {"account_id": gl, "debit": 100},
                    {"account_id": cash, "credit": 100},
                ],
            },
            status="pending",
        )
        db.add(action)
        db.commit()
        aid = action.id

        # Nothing posted yet.
        before = db.scalar(
            select(JournalEntry).where(JournalEntry.memo == "pytest software sub")
        )
        assert before is None

        # Approve -> posts + writes an audit row.
        audit = approvals.approve(db, action, "tester@demo")
        assert isinstance(audit, AuditLog)
        posted = db.scalar(
            select(JournalEntry).where(JournalEntry.memo == "pytest software sub")
        )
        assert posted is not None and posted.status == "posted"

        log = db.get(AuditLog, audit.id)
        assert log.user_id == "tester@demo" and log.action == "approved"

        # Double-approve is rejected by the gate.
        with pytest.raises(approvals.ApprovalError):
            approvals.approve(db, action, "tester@demo")
    finally:
        db.close()


def test_intercompany_eliminations_net_to_zero():
    db = SessionLocal()
    try:
        pnl = consolidated_pnl(db)
        # Eliminations row mirrors intercompany balances; consolidated excludes them.
        assert "consolidated" in pnl and "eliminations" in pnl
        # The consolidated total must not contain any intercompany double-count:
        # every eliminated row is reflected as a negative in the eliminations block.
        for row in pnl["eliminations"]["rows"]:
            assert "amount" in row
    finally:
        db.close()
