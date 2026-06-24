from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import Account, BankTransaction, JournalEntry
from app.security import current_user

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("/entries")
def journal_entries(
    entity_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    stmt = select(JournalEntry).order_by(JournalEntry.created_at.desc())
    if entity_id:
        stmt = stmt.where(JournalEntry.entity_id == entity_id)
    if status:
        stmt = stmt.where(JournalEntry.status == status)
    out = []
    for e in db.scalars(stmt):
        out.append(
            {
                "id": e.id,
                "entity_id": e.entity_id,
                "date": e.date.isoformat(),
                "memo": e.memo,
                "status": e.status,
                "created_by_agent": e.created_by_agent,
                "lines": [
                    {
                        "account_id": l.account_id,
                        "account_code": l.account.code,
                        "account_name": l.account.name,
                        "debit": float(l.debit),
                        "credit": float(l.credit),
                    }
                    for l in e.lines
                ],
            }
        )
    return out


@router.get("/bank")
def bank_transactions(
    entity_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    stmt = select(BankTransaction).order_by(BankTransaction.id)
    if entity_id:
        stmt = stmt.where(BankTransaction.entity_id == entity_id)
    if status:
        stmt = stmt.where(BankTransaction.status == status)
    return [
        {
            "id": b.id,
            "entity_id": b.entity_id,
            "date": b.date.isoformat(),
            "amount": float(b.amount),
            "description": b.description,
            "status": b.status,
            "matched_journal_entry_id": b.matched_journal_entry_id,
        }
        for b in db.scalars(stmt)
    ]


@router.get("/accounts")
def accounts(
    entity_id: int | None = None,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    stmt = select(Account).order_by(Account.entity_id, Account.code)
    if entity_id:
        stmt = stmt.where(Account.entity_id == entity_id)
    return [
        {
            "id": a.id,
            "entity_id": a.entity_id,
            "code": a.code,
            "name": a.name,
            "type": a.type,
            "is_intercompany": a.is_intercompany,
        }
        for a in db.scalars(stmt)
    ]
