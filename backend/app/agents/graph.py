"""The Orchestrator: a LangGraph supervisor that classifies an incoming event
and routes it to the right specialist agent. It does no accounting math itself.

State flows: classify -> (conditional edge) -> one specialist node -> END.
The DB session is passed via a contextvar so graph state stays serializable.
"""
from __future__ import annotations

import contextvars
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents import ar_clerk, bill_handler, categorizer, closer, consolidator
from app.events.types import (
    AR_OVERDUE,
    BANK_LINE,
    CLOSE_TRIGGER,
    INTERCOMPANY,
    INVOICE_RECEIVED,
)
from app.llm.client import complete_json

# event type -> specialist node name
ROUTING = {
    BANK_LINE: "categorizer",
    INVOICE_RECEIVED: "bill_handler",
    AR_OVERDUE: "ar_clerk",
    INTERCOMPANY: "consolidator",
    CLOSE_TRIGGER: "closer",
}

_db_ctx: contextvars.ContextVar[Session] = contextvars.ContextVar("orchestrator_db")

ORCH_SYSTEM = (
    "You are the Orchestrator of an AI accounting team. You are a traffic cop: "
    "classify the event and pick exactly one specialist. Do not do accounting. "
    "Specialists: categorizer, bill_handler, ar_clerk, consolidator, closer."
)


class GState(TypedDict, total=False):
    event_type: str
    data: dict
    route: str
    action_ids: list[int]
    source_event_id: str | None


def _classify(state: GState) -> GState:
    etype = state["event_type"]
    default = ROUTING.get(etype, "categorizer")
    decision = complete_json(
        "orchestrator",
        ORCH_SYSTEM,
        f"Event type: {etype}. Data: {state['data']}. "
        f"Return JSON {{route}} where route is one specialist name.",
        mock=lambda _u: {"route": default},
    )
    route = decision.get("route", default)
    if route not in ROUTING.values():
        route = default
    state["route"] = route
    return state


def _make_specialist(fn):
    def node(state: GState) -> GState:
        db = _db_ctx.get()
        action = fn(db, {**state["data"], "source_event_id": state.get("source_event_id")})
        ids = state.get("action_ids", [])
        if isinstance(action, list):
            ids += [a.id for a in action if a]
        elif action:
            ids.append(action.id)
        state["action_ids"] = ids
        return state

    return node


def _build():
    g = StateGraph(GState)
    g.add_node("classify", _classify)
    g.add_node("categorizer", _make_specialist(categorizer.run))
    g.add_node("bill_handler", _make_specialist(bill_handler.run))
    g.add_node("ar_clerk", _make_specialist(ar_clerk.run))
    g.add_node("consolidator", _make_specialist(consolidator.run))
    g.add_node("closer", _make_specialist(closer.run))

    g.add_edge(START, "classify")
    g.add_conditional_edges("classify", lambda s: s["route"])
    for node in ROUTING.values():
        g.add_edge(node, END)
    return g.compile()


_graph = None


def run_event(db: Session, event_type: str, data: dict, source_event_id: str | None = None) -> list[int]:
    """Entry point used by the worker. Returns ids of ProposedActions created."""
    global _graph
    if _graph is None:
        _graph = _build()
    token = _db_ctx.set(db)
    try:
        result = _graph.invoke(
            {"event_type": event_type, "data": data, "source_event_id": source_event_id}
        )
        return result.get("action_ids", [])
    finally:
        _db_ctx.reset(token)
