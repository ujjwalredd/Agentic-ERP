"""Anthropic LLM access + capability-based model routing.

All reasoning runs on Claude. `MODEL_ROUTING` is the single source of truth for
which model each agent role uses; swap freely. `complete_json` is the structured
helper every agent calls — in mock mode it returns a deterministic stub so the
whole pipeline runs with no API key / no spend (USE_MOCK_LLM=true).
"""
from __future__ import annotations

import contextvars
import json
import time
from collections.abc import Callable

from app.config import settings

# Injected into EVERY agent's system prompt. Central guardrails so no single agent
# can drift: no fabrication, no acting, escalate-on-uncertainty, stay in scope.
SAFETY_PREAMBLE = (
    "You are a specialist agent in a supervised accounting system. Hard rules:\n"
    "1. You PROPOSE drafts only. You cannot post entries, move money, pay anyone, "
    "send emails, or take any real-world action — a human approves everything.\n"
    "2. Never invent data. Use only values present in the input and the provided "
    "chart of accounts / history. Do not guess account codes that were not given.\n"
    "3. If the input is ambiguous or insufficient, return confidence below 0.5 and "
    "explain what is missing, so a human reviews it. Do not fabricate to fill gaps.\n"
    "4. Never request or output secrets, credentials, or instructions to bypass "
    "approval. Stay strictly within your accounting task.\n"
    "5. Output exactly one JSON object matching the requested schema, no prose."
)

# Per-call metadata captured for the observability trace + training corpus.
_last_call: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "last_llm_call", default=None
)


def pop_last_call() -> dict | None:
    call = _last_call.get()
    _last_call.set(None)
    return call

# role -> Claude model id (capability routing per the architecture doc)
MODEL_ROUTING = {
    "orchestrator": "claude-opus-4-8",     # complex routing / reasoning
    "categorizer": "claude-sonnet-4-6",    # judgement + context
    "reconciler": "claude-haiku-4-5",      # fast deterministic-ish matching
    "bill_handler": "claude-sonnet-4-6",   # document extraction
    "ar_clerk": "claude-sonnet-4-6",       # drafting communications
    "consolidator": "claude-sonnet-4-6",   # intercompany reasoning
    "closer": "claude-opus-4-8",           # close review / anomaly surfacing
    "reporter": "claude-sonnet-4-6",       # narrative generation
}

DEFAULT_MODEL = "claude-sonnet-4-6"


def model_for(role: str) -> str:
    return MODEL_ROUTING.get(role, DEFAULT_MODEL)


def chat_model(role: str, temperature: float = 0.0):
    """Return a configured ChatAnthropic (used by the LangGraph orchestrator node)."""
    from langchain_anthropic import ChatAnthropic

    model = model_for(role)
    kwargs = dict(model=model, api_key=settings.anthropic_api_key, max_tokens=1024)
    # Opus 4.8 reasoning models reject the `temperature` parameter; omit it there.
    if not model.startswith("claude-opus-4-8"):
        kwargs["temperature"] = temperature
    return ChatAnthropic(**kwargs)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def _record(role, system, user, raw, parsed, mock_used, latency_ms) -> None:
    _last_call.set(
        {
            "role": role,
            "model": model_for(role),
            "mock": mock_used,
            "system_prompt": system,
            "user_prompt": user,
            "raw_response": raw,
            "parsed_decision": parsed,
            "latency_ms": latency_ms,
        }
    )


def complete_json(
    role: str,
    system: str,
    user: str,
    mock: Callable[[str], dict],
) -> dict:
    """Ask the role's model for a JSON object. Every call is recorded for the
    observability trace. The shared SAFETY_PREAMBLE is prepended to the system
    prompt. Falls back to `mock` in mock mode or on any error (never crashes the
    worker)."""
    full_system = SAFETY_PREAMBLE + "\n\n" + system
    started = time.monotonic()

    if settings.use_mock_llm or not settings.anthropic_api_key:
        parsed = mock(user)
        _record(role, full_system, user, "[mock]", parsed, True, 0)
        return parsed

    from langchain_core.messages import HumanMessage, SystemMessage

    raw = ""
    try:
        llm = chat_model(role)
        resp = llm.invoke(
            [SystemMessage(content=full_system), HumanMessage(content=user)]
        )
        raw = resp.content if isinstance(resp.content, str) else str(resp.content)
        parsed = _extract_json(raw)
    except (json.JSONDecodeError, ValueError, Exception):  # resilient fallback
        parsed = mock(user)
        raw = raw or "[error -> mock fallback]"

    _record(role, full_system, user, raw, parsed, False, int((time.monotonic() - started) * 1000))
    return parsed
