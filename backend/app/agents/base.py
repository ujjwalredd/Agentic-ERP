"""Shared agent helpers. Agents NEVER post to the ledger directly — they only
write ProposedAction drafts that a human approves later."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Account, AgentTrace, ProposedAction
from app.llm.client import pop_last_call


def account_id(db: Session, entity_id: int, code: str) -> int | None:
    a = db.scalar(
        select(Account).where(Account.entity_id == entity_id, Account.code == code)
    )
    return a.id if a else None


def pending_exists(db: Session, key: str, value) -> bool:
    """True if a still-pending draft already references this source (e.g. a bank
    line / bill). Used to make agent runs idempotent — re-firing the same event
    must not create duplicate drafts that could each be approved (double-post)."""
    stmt = (
        select(ProposedAction.id)
        .where(
            ProposedAction.status == "pending",
            ProposedAction.payload[key].astext == str(value),
        )
        .limit(1)
    )
    return db.scalar(stmt) is not None


def record_trace(
    db: Session,
    *,
    agent: str | None = None,
    proposed_action_id: int | None = None,
    confidence: float = 0.0,
    commit: bool = False,
) -> None:
    """Persist the most recent LLM call (orchestrator routing or a specialist
    decision) to AgentTrace for full observability + the training corpus."""
    call = pop_last_call()
    if call is None:
        return
    db.add(
        AgentTrace(
            agent=agent or call["role"],
            role=call["role"],
            model=call["model"],
            mock=call["mock"],
            system_prompt=call["system_prompt"],
            user_prompt=call["user_prompt"],
            raw_response=call["raw_response"],
            parsed_decision=call["parsed_decision"],
            confidence=round(float(confidence), 3),
            latency_ms=call["latency_ms"],
            proposed_action_id=proposed_action_id,
        )
    )
    if commit:
        db.commit()


def propose(
    db: Session,
    *,
    agent: str,
    action_type: str,
    summary: str,
    confidence: float,
    payload: dict,
    source_event_id: str | None = None,
) -> ProposedAction:
    action = ProposedAction(
        agent=agent,
        action_type=action_type,
        summary=summary,
        confidence=round(float(confidence), 3),
        payload=payload,
        source_event_id=source_event_id,
        status="pending",
    )
    db.add(action)
    db.flush()

    # Observability + training corpus: persist the LLM decision that produced this
    # draft, linked to it. The later human approve/reject becomes the label.
    record_trace(db, agent=agent, proposed_action_id=action.id, confidence=confidence)

    db.commit()
    db.refresh(action)
    return action
