"""Continuous multi-entity consolidation with intercompany elimination.

Recomputed on every `entry.posted` event (no month-end batch). Intercompany
accounts (Account.is_intercompany) are eliminated in the consolidated column.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Account, Entity, JournalEntry, JournalLine


def _pnl_amount(type_: str, debit: Decimal, credit: Decimal) -> Decimal:
    """P&L-positive convention: revenue = credit-debit, expense = debit-credit."""
    if type_ == "revenue":
        return credit - debit
    if type_ == "expense":
        return debit - credit
    return Decimal("0")


def _entity_rows(db: Session, entity_id: int) -> list[dict]:
    """Per-account P&L amounts for posted entries of one entity."""
    rows = db.execute(
        select(
            Account.code,
            Account.name,
            Account.type,
            Account.is_intercompany,
            JournalLine.debit,
            JournalLine.credit,
        )
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(
            JournalEntry.entity_id == entity_id,
            JournalEntry.status == "posted",
            Account.type.in_(("revenue", "expense")),
        )
    ).all()

    agg: dict[str, dict] = {}
    for code, name, type_, ic, debit, credit in rows:
        amt = _pnl_amount(type_, debit or Decimal(0), credit or Decimal(0))
        slot = agg.setdefault(
            code,
            {"code": code, "name": name, "type": type_, "is_intercompany": ic, "amount": Decimal(0)},
        )
        slot["amount"] += amt
    return list(agg.values())


def _summarize(rows: list[dict]) -> dict:
    revenue = sum((r["amount"] for r in rows if r["type"] == "revenue"), Decimal(0))
    expense = sum((r["amount"] for r in rows if r["type"] == "expense"), Decimal(0))
    return {
        "revenue": float(revenue),
        "expense": float(expense),
        "net_income": float(revenue - expense),
    }


def consolidated_pnl(db: Session) -> dict:
    entities = list(db.scalars(select(Entity)))

    per_entity = []
    all_rows: list[dict] = []
    for ent in entities:
        rows = _entity_rows(db, ent.id)
        all_rows.extend(rows)
        per_entity.append(
            {
                "entity_id": ent.id,
                "entity": ent.name,
                "rows": [{**r, "amount": float(r["amount"])} for r in rows],
                **_summarize(rows),
            }
        )

    # Eliminations: everything booked to an intercompany account nets out.
    elim_rows = [r for r in all_rows if r["is_intercompany"]]
    keep_rows = [r for r in all_rows if not r["is_intercompany"]]

    eliminations = {
        "rows": [
            {"name": r["name"], "type": r["type"], "amount": -float(r["amount"])}
            for r in elim_rows
        ],
        **{
            k: -v
            for k, v in _summarize(elim_rows).items()
        },
    }
    consolidated = _summarize(keep_rows)

    return {
        "entities": per_entity,
        "eliminations": eliminations,
        "consolidated": consolidated,
    }
