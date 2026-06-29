from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db.base import Base

# ---- enums as plain strings (kept simple for a prototype) --------------------
ACCOUNT_TYPES = ("asset", "liability", "equity", "revenue", "expense")
ENTRY_STATUS = ("draft", "posted")
ACTION_STATUS = ("pending", "approved", "rejected")
BILL_STATUS = ("staged", "booked", "paid")
INVOICE_STATUS = ("open", "overdue", "reminded", "paid")


USER_ROLES = ("controller", "viewer")


class User(Base):
    """A human operator. `controller` can approve/reject/edit + manage rules;
    `viewer` is read-only. The login identity (email) is what gets stamped into
    the immutable AuditLog, so accountability is per-person, not a shared token."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="controller")  # USER_ROLES
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("entities.id"), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD")

    parent: Mapped[Entity | None] = relationship(remote_side=[id], backref="children")
    accounts: Mapped[list[Account]] = relationship(back_populates="entity")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"))
    code: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(20))  # one of ACCOUNT_TYPES
    is_intercompany: Mapped[bool] = mapped_column(Boolean, default=False)

    entity: Mapped[Entity] = relationship(back_populates="accounts")


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"))
    date: Mapped[dt.date] = mapped_column(Date, default=dt.date.today)
    memo: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(10), default="draft")  # ENTRY_STATUS
    created_by_agent: Mapped[str] = mapped_column(String(40), default="system")
    source_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())

    lines: Mapped[list[JournalLine]] = relationship(
        back_populates="entry", cascade="all, delete-orphan"
    )


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    journal_entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    debit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    credit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)

    entry: Mapped[JournalEntry] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship()


class BankTransaction(Base):
    __tablename__ = "bank_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"))
    date: Mapped[dt.date] = mapped_column(Date, default=dt.date.today)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))  # +inflow / -outflow
    description: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="unmatched")  # unmatched/matched
    matched_journal_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("journal_entries.id"), nullable=True
    )


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"))
    vendor: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    due_date: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="staged")  # BILL_STATUS
    lines: Mapped[dict] = mapped_column(JSONB, default=dict)


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey("entities.id"))
    customer: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    due_date: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="open")  # INVOICE_STATUS
    lines: Mapped[dict] = mapped_column(JSONB, default=dict)


class ProposedAction(Base):
    """The HITL draft queue. Agents write here; nothing posts until approved."""

    __tablename__ = "proposed_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(40))
    action_type: Mapped[str] = mapped_column(String(40))
    summary: Mapped[str] = mapped_column(String(255))
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0)
    payload: Mapped[dict] = mapped_column(JSONB)  # the mutation to apply on approve
    status: Mapped[str] = mapped_column(String(10), default="pending")  # ACTION_STATUS
    source_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    """Immutable trail. One row per approve/reject decision."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    user_id: Mapped[str] = mapped_column(String(80))
    agent: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(40))  # approved / rejected
    proposed_action_id: Mapped[int] = mapped_column(ForeignKey("proposed_actions.id"))
    before: Mapped[dict] = mapped_column(JSONB, default=dict)
    after: Mapped[dict] = mapped_column(JSONB, default=dict)


class AgentTrace(Base):
    """Full observability + training corpus. One row per agent LLM decision,
    capturing the exact input, prompts, model, raw + parsed output, and latency.
    Linked to the ProposedAction it produced; the later human approve/reject on
    that action becomes the supervision label (see /observability/training-data).
    """

    __tablename__ = "agent_traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
    agent: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(40))          # llm routing role
    model: Mapped[str] = mapped_column(String(60))
    mock: Mapped[bool] = mapped_column(Boolean, default=False)
    event_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    event_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    user_prompt: Mapped[str] = mapped_column(Text, default="")
    raw_response: Mapped[str] = mapped_column(Text, default="")
    parsed_decision: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    proposed_action_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposed_actions.id"), nullable=True
    )


class VectorDoc(Base):
    """Categorizer memory: past categorizations embedded for similarity recall."""

    __tablename__ = "vector_docs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), default="txn_category")
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dim))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class Rule(Base):
    """Explicit, codified accounting knowledge. Recurring approved/corrected
    patterns become deterministic rules — no LLM, so no hallucination. A matched
    rule can pre-fill the GL account and (if auto_approve) let the draft finalize
    without a human click."""

    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_id: Mapped[int | None] = mapped_column(
        ForeignKey("entities.id"), nullable=True
    )  # null = applies to all entities
    match_type: Mapped[str] = mapped_column(String(20), default="vendor_contains")  # | regex
    pattern: Mapped[str] = mapped_column(String(255))
    account_code: Mapped[str] = mapped_column(String(20))
    tags: Mapped[dict] = mapped_column(JSONB, default=dict)
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    min_confidence: Mapped[float] = mapped_column(Numeric(4, 3), default=0.9)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual|correction|approval
    hits: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(80), default="demo-user")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())


class Correction(Base):
    """The richest learning signal: what a human changed about an agent's proposal
    and why. Edits and reject-reasons become high-weight training examples and seed
    new Rules."""

    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    proposed_action_id: Mapped[int] = mapped_column(ForeignKey("proposed_actions.id"))
    user_id: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(10))  # edit | reject
    reason: Mapped[str] = mapped_column(Text, default="")
    before: Mapped[dict] = mapped_column(JSONB, default=dict)
    after: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, server_default=func.now())
