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
    call = pop_last_call()
    if call is not None:
        db.add(
            AgentTrace(
                agent=agent,
                role=call["role"],
                model=call["model"],
                mock=call["mock"],
                event_data=payload.get("source", {}),
                system_prompt=call["system_prompt"],
                user_prompt=call["user_prompt"],
                raw_response=call["raw_response"],
                parsed_decision=call["parsed_decision"],
                confidence=round(float(confidence), 3),
                latency_ms=call["latency_ms"],
                proposed_action_id=action.id,
            )
        )

    db.commit()
    db.refresh(action)
    return action
