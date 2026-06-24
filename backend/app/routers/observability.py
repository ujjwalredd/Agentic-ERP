"""Observability + learning loop.

Every agent decision is logged to AgentTrace. Joined with the human approve/reject
on the resulting ProposedAction, each trace becomes a supervised training example —
the dataset for fine-tuning / evals / building the agents' "expert memory".
"""
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import AgentTrace, AuditLog, Correction, ProposedAction
from app.security import current_user

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/traces")
def traces(
    agent: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    stmt = select(AgentTrace).order_by(AgentTrace.timestamp.desc()).limit(limit)
    if agent:
        stmt = stmt.where(AgentTrace.agent == agent)
    return [
        {
            "id": t.id,
            "timestamp": t.timestamp.isoformat(),
            "agent": t.agent,
            "model": t.model,
            "mock": t.mock,
            "confidence": float(t.confidence),
            "latency_ms": t.latency_ms,
            "user_prompt": t.user_prompt,
            "raw_response": t.raw_response,
            "parsed_decision": t.parsed_decision,
            "proposed_action_id": t.proposed_action_id,
        }
        for t in db.scalars(stmt)
    ]


@router.get("/stats")
def stats(db: Session = Depends(get_db), user: str = Depends(current_user)):
    by_agent = db.execute(
        select(
            AgentTrace.agent,
            func.count(AgentTrace.id),
            func.avg(AgentTrace.confidence),
            func.avg(AgentTrace.latency_ms),
        ).group_by(AgentTrace.agent)
    ).all()
    decisions = db.execute(
        select(AuditLog.action, func.count(AuditLog.id)).group_by(AuditLog.action)
    ).all()
    return {
        "agents": [
            {
                "agent": a,
                "decisions": n,
                "avg_confidence": round(float(c or 0), 3),
                "avg_latency_ms": round(float(l or 0), 1),
            }
            for a, n, c, l in by_agent
        ],
        "human_decisions": {action: n for action, n in decisions},
        "total_traces": db.scalar(select(func.count(AgentTrace.id))) or 0,
    }


def _labeled_rows(db: Session, only_labeled: bool):
    """Join trace -> proposed action -> human decision to build (input, output, label).
    Human corrections are folded in as the highest-signal examples (label
    'corrected', carrying the reason + before/after diff)."""
    corrections = {}
    for c in db.scalars(select(Correction)):
        corrections.setdefault(c.proposed_action_id, c)

    rows = db.execute(
        select(AgentTrace, ProposedAction, AuditLog)
        .join(ProposedAction, ProposedAction.id == AgentTrace.proposed_action_id)
        .outerjoin(AuditLog, AuditLog.proposed_action_id == ProposedAction.id)
        .order_by(AgentTrace.timestamp)
    ).all()
    out = []
    for trace, action, audit in rows:
        corr = corrections.get(action.id)
        label = (
            "corrected"
            if corr and corr.kind == "edit"
            else (audit.action if audit else action.status)
        )
        if only_labeled and label not in ("approved", "rejected", "corrected"):
            continue
        out.append(
            {
                "agent": trace.agent,
                "model": trace.model,
                "system": trace.system_prompt,
                "input": trace.user_prompt,
                "output": trace.parsed_decision,
                "confidence": float(trace.confidence),
                # supervision signal: did the human accept, reject, or correct it?
                "human_label": label,
                "reward": 1 if label == "approved" else (0 if label == "rejected" else None),
                # the richest signal: what the human changed and why
                "correction": (
                    {"reason": corr.reason, "before": corr.before, "after": corr.after}
                    if corr
                    else None
                ),
            }
        )
    return out


@router.get("/training-data")
def training_data(
    labeled_only: bool = True,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    """Labeled corpus as JSON (each row = one supervised example)."""
    return _labeled_rows(db, labeled_only)


@router.get("/training-data.jsonl", response_class=PlainTextResponse)
def training_data_jsonl(
    labeled_only: bool = True,
    db: Session = Depends(get_db),
    user: str = Depends(current_user),
):
    """Same corpus as downloadable JSONL — ready for an SFT / eval pipeline."""
    return "\n".join(json.dumps(r) for r in _labeled_rows(db, labeled_only))
