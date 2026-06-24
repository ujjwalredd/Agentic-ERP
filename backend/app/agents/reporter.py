"""The Reporter: generate a narrative over the real-time consolidated P&L.

Numbers come from services.consolidation (deterministic); the LLM only writes the
commentary. Proposes an informational `note` for the human to acknowledge.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.base import propose
from app.db.models import ProposedAction
from app.llm.client import complete_json
from app.services.consolidation import consolidated_pnl

AGENT = "Reporter"
SYSTEM = (
    "You are a financial reporter. Write a concise two-sentence commentary using ONLY "
    "the consolidated P&L figures provided. Do not state any number that is not in the "
    "input, and do not editorialize beyond what the figures support. Highlight net "
    "income and the effect of intercompany eliminations."
)


def _mock(_user: str, pnl: dict) -> dict:
    c = pnl["consolidated"]
    elim = pnl["eliminations"]
    return {
        "commentary": (
            f"Consolidated net income is {c['net_income']:.2f} on revenue "
            f"{c['revenue']:.2f}. Intercompany eliminations removed "
            f"{abs(elim['revenue']):.2f} of internal revenue."
        ),
        "confidence": 0.95,
    }


def run(db: Session, data: dict) -> ProposedAction | None:
    pnl = consolidated_pnl(db)
    decision = complete_json(
        "reporter",
        SYSTEM,
        f"Consolidated figures: {pnl['consolidated']}; eliminations: {pnl['eliminations']}. "
        "Return JSON {commentary, confidence}.",
        mock=lambda _u: _mock(_u, pnl),
    )
    return propose(
        db,
        agent=AGENT,
        action_type="note",
        summary="Consolidated P&L report ready",
        confidence=decision.get("confidence", 0.9),
        payload={
            "note": decision.get("commentary"),
            "consolidated": pnl["consolidated"],
            "eliminations": pnl["eliminations"],
        },
        source_event_id=data.get("source_event_id"),
    )
