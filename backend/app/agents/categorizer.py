"""The Categorizer: book a raw bank line to the right GL account.

Queries pgvector for similar past categorizations, asks Claude to pick the GL
account + tags, and stages a draft journal entry. On approval the categorization
is written back to vector memory so the agent "learns".
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.base import account_id, pending_exists, propose
from app.db.models import Account, ProposedAction
from app.llm.client import complete_json
from app.services import approvals, rules, vectors

AGENT = "Categorizer"

SYSTEM = (
    "You are an expert bookkeeper categorizing a bank transaction. Choose the GL "
    "account ONLY from the account codes shown in the 'similar past categorizations' "
    "examples — do not invent a code. If none clearly fit, pick the closest example "
    "and set confidence below 0.5 so a human reviews it. Base the choice on the "
    "vendor/description, not assumptions about the business."
)


def _mock(_user: str, top_code: str, top_name: str) -> dict:
    return {
        "account_code": top_code,
        "account_name": top_name,
        "tags": ["auto"],
        "confidence": 0.82,
        "reasoning": "Matched nearest historical categorization.",
    }


def run(db: Session, data: dict) -> ProposedAction | None:
    desc = data["description"]
    entity_id = data["entity_id"]
    amount = float(data["amount"])

    # 0. idempotency: skip if a pending draft already exists for this bank line
    bt_id = data.get("bank_transaction_id")
    if bt_id and pending_exists(db, "bank_transaction_id", bt_id):
        return None

    # 1. RULE-FIRST: a matching rule is deterministic codified knowledge — use it
    # directly (no LLM, no hallucination) and mark the draft auto-approve eligible.
    rule = rules.match(db, entity_id, desc)
    rule_id = None
    rule_auto = False
    confidence = 0.8
    top = {"account_code": "5100", "account_name": "Office Supplies"}  # safe fallback
    if rule is not None:
        rules.bump_hits(db, rule)
        _gl = account_id(db, entity_id, rule.account_code)
        acct = db.get(Account, _gl) if _gl else None
        code = rule.account_code
        name = acct.name if acct else rule.account_code
        confidence = max(float(rule.min_confidence), 0.96)
        rule_id, rule_auto = rule.id, rule.auto_approve
        decision = {"account_code": code, "account_name": name, "confidence": confidence,
                    "reasoning": f"rule #{rule.id}"}
    else:
        # 2. recall similar past categorizations + ask the model
        neighbors = vectors.similar(db, desc, k=3)
        if neighbors:
            top = neighbors[0].meta
        examples = "\n".join(
            f"- '{n.text}' -> {n.meta.get('account_code')} {n.meta.get('account_name')}"
            for n in neighbors
        ) or "(no history)"
        user = (
            f"Transaction: '{desc}', amount {amount:+.2f}.\n"
            f"Similar past categorizations:\n{examples}\n"
            "Return JSON: {account_code, account_name, tags[], confidence, reasoning}."
        )
        decision = complete_json(
            "categorizer",
            SYSTEM,
            user,
            mock=lambda u: _mock(u, top["account_code"], top["account_name"]),
        )
        code = decision.get("account_code", top["account_code"])
        name = decision.get("account_name", top["account_name"])
        confidence = decision.get("confidence", 0.8)
    cash_id = account_id(db, entity_id, "1000")
    gl_id = account_id(db, entity_id, code)
    if gl_id is None:  # model hallucinated a code -> fall back to nearest neighbor
        code, name = top["account_code"], top["account_name"]
        gl_id = account_id(db, entity_id, code)

    # 3. build a balanced draft entry (outflow: Dr expense / Cr cash; inflow reverse)
    mag = abs(amount)
    if amount < 0:
        lines = [
            {"account_id": gl_id, "debit": mag},
            {"account_id": cash_id, "credit": mag},
        ]
    else:
        rev_id = account_id(db, entity_id, "4000")
        lines = [
            {"account_id": cash_id, "debit": mag},
            {"account_id": rev_id, "credit": mag},
        ]
        code, name = "4000", "Product Revenue"
        # an inflow booked to revenue is not an expense-rule match; never auto-post it
        rule_id, rule_auto = None, False

    payload = {
        "agent": AGENT,
        "entity_id": entity_id,
        "memo": f"{desc} -> {name}",
        "lines": lines,
        "bank_transaction_id": data.get("bank_transaction_id"),
        "source_event_id": data.get("source_event_id"),
        # written to vector memory on approval -> the learning loop
        "memory": {"text": desc, "meta": {"account_code": code, "account_name": name}},
        # knowledge-loop metadata
        "rule_id": rule_id,
        "auto_approve": bool(rule_auto),
        "description": desc,
    }
    action = propose(
        db,
        agent=AGENT,
        action_type="book_journal_entry",
        summary=f"Book {mag:.2f} '{desc}' to {code} {name}"
        + (" [rule]" if rule_id else ""),
        confidence=confidence,
        payload=payload,
        source_event_id=data.get("source_event_id"),
    )
    # Gated autonomy: an auto_approve rule match finalizes without a human click.
    approvals.auto_approve_if_eligible(db, action)
    return action
