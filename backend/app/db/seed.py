"""Idempotent demo seed: entities, chart of accounts, bank feed, AP/AR, vector memory."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    Account,
    Bill,
    BankTransaction,
    Entity,
    Invoice,
    JournalEntry,
    JournalLine,
    User,
    VectorDoc,
)

TODAY = dt.date(2026, 6, 23)

# Chart-of-accounts template applied to every entity. (code, name, type, intercompany)
COA_TEMPLATE = [
    ("1000", "Cash", "asset", False),
    ("1100", "Accounts Receivable", "asset", False),
    ("1200", "Intercompany Receivable", "asset", True),
    ("2000", "Accounts Payable", "liability", False),
    ("2100", "Intercompany Payable", "liability", True),
    ("3000", "Owner Equity", "equity", False),
    ("4000", "Product Revenue", "revenue", False),
    ("4100", "Intercompany Revenue", "revenue", True),
    ("5000", "Software Subscriptions", "expense", False),
    ("5100", "Office Supplies", "expense", False),
    ("5200", "Cost of Goods Sold", "expense", False),
    ("5300", "Intercompany Expense", "expense", True),
]


def _acct(db: Session, entity_id: int, code: str) -> Account:
    return db.scalar(
        select(Account).where(Account.entity_id == entity_id, Account.code == code)
    )


def seed_users(db: Session) -> None:
    """Seed a demo controller for JWT auth (idempotent). Only runs when JWT is
    configured, so open-dev/mock setups need no user table content."""
    if not settings.jwt_secret:
        return
    if db.scalar(select(User).where(User.email == settings.seed_user_email)):
        return
    from app.security import hash_password

    db.add(
        User(
            email=settings.seed_user_email,
            password_hash=hash_password(settings.seed_user_password),
            role="controller",
        )
    )
    db.commit()


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(Entity).limit(1)) is not None:
        return  # already seeded

    # ---- entities (ParentCo with two subsidiaries) --------------------------
    parent = Entity(name="ParentCo", currency="USD")
    db.add(parent)
    db.flush()
    sub_a = Entity(name="SubA", parent_id=parent.id, currency="USD")
    sub_b = Entity(name="SubB", parent_id=parent.id, currency="USD")
    db.add_all([sub_a, sub_b])
    db.flush()

    # ---- chart of accounts for each entity ----------------------------------
    for ent in (parent, sub_a, sub_b):
        for code, name, type_, ic in COA_TEMPLATE:
            db.add(
                Account(
                    entity_id=ent.id, code=code, name=name, type=type_, is_intercompany=ic
                )
            )
    db.flush()

    # ---- opening balances: posted equity injection so reports aren't empty ---
    for ent in (sub_a, sub_b):
        je = JournalEntry(
            entity_id=ent.id,
            date=TODAY - dt.timedelta(days=30),
            memo="Opening capital",
            status="posted",
            created_by_agent="system",
        )
        db.add(je)
        db.flush()
        db.add_all(
            [
                JournalLine(
                    journal_entry_id=je.id,
                    account_id=_acct(db, ent.id, "1000").id,
                    debit=Decimal("50000"),
                ),
                JournalLine(
                    journal_entry_id=je.id,
                    account_id=_acct(db, ent.id, "3000").id,
                    credit=Decimal("50000"),
                ),
            ]
        )

    # ---- raw bank feed for SubA (unmatched, drives the Categorizer) ----------
    bank_lines = [
        ("AWS WEB SERVICES", Decimal("-340.00")),
        ("NOTION LABS SUBSCRIPTION", Decimal("-48.00")),
        ("STAPLES STORE #1123", Decimal("-86.50")),
        ("GITHUB INC", Decimal("-21.00")),
        ("STRIPE PAYOUT", Decimal("4200.00")),
        ("UNITED AIRLINES TICKET", Decimal("-512.30")),
        ("WEWORK MONTHLY", Decimal("-650.00")),
        ("ZOOM VIDEO COMMS", Decimal("-15.99")),
    ]
    for desc, amt in bank_lines:
        db.add(
            BankTransaction(
                entity_id=sub_a.id, date=TODAY, amount=amt, description=desc
            )
        )

    # ---- intercompany bank line on SubB: payment to SubA for services --------
    db.add(
        BankTransaction(
            entity_id=sub_b.id,
            date=TODAY,
            amount=Decimal("-2000.00"),
            description="INTERCOMPANY SERVICE FEE - SubA",
        )
    )

    # ---- AR: one overdue invoice (drives AR Clerk) --------------------------
    db.add(
        Invoice(
            entity_id=sub_a.id,
            customer="Acme Corp",
            amount=Decimal("3500.00"),
            due_date=TODAY - dt.timedelta(days=14),
            status="overdue",
            lines={"items": [{"desc": "Consulting", "amount": 3500.0}]},
        )
    )

    # ---- AP: one staged vendor bill (drives Bill Handler) -------------------
    db.add(
        Bill(
            entity_id=sub_a.id,
            vendor="Cloudflare",
            amount=Decimal("200.00"),
            due_date=TODAY + dt.timedelta(days=20),
            status="staged",
            lines={"items": [{"desc": "CDN annual", "amount": 200.0}]},
        )
    )

    # ---- Categorizer memory: a few past categorizations ---------------------
    from app.services.vectors import embed

    memory = [
        ("AWS WEB SERVICES cloud hosting", "5000", "Software Subscriptions"),
        ("GITHUB code hosting subscription", "5000", "Software Subscriptions"),
        ("STAPLES office supplies store", "5100", "Office Supplies"),
        ("UNITED AIRLINES flight travel", "5200", "Cost of Goods Sold"),
    ]
    for text, code, name in memory:
        db.add(
            VectorDoc(
                kind="txn_category",
                text=text,
                embedding=embed(text),
                meta={"account_code": code, "account_name": name},
            )
        )

    db.commit()
