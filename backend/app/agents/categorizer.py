"""The Categorizer: book a raw bank line to the right GL account.

Queries pgvector for similar past categorizations, asks Claude to pick the GL
account + tags, and stages a draft journal entry. On approval the categorization
is written back to vector memory so the agent "learns".
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.base import account_id, propose
from app.db.models import ProposedAction
from app.llm.client import complete_json
from app.services import vectors

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

    # 1. recall similar past categorizations
    neighbors = vectors.similar(db, desc, k=3)
    top = neighbors[0].meta if neighbors else {"account_code": "5100", "account_name": "Office Supplies"}
    examples = "\n".join(
        f"- '{n.text}' -> {n.meta.get('account_code')} {n.meta.get('account_name')}"
        for n in neighbors
    ) or "(no history)"

    # 2. ask the model (or mock) for the GL account
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

    payload = {
        "agent": AGENT,
        "entity_id": entity_id,
        "memo": f"{desc} -> {name}",
        "lines": lines,
        "bank_transaction_id": data.get("bank_transaction_id"),
        "source_event_id": data.get("source_event_id"),
        # written to vector memory on approval -> the learning loop
        "memory": {"text": desc, "meta": {"account_code": code, "account_name": name}},
    }
    return propose(
        db,
        agent=AGENT,
        action_type="book_journal_entry",
        summary=f"Book {mag:.2f} '{desc}' to {code} {name}",
        confidence=decision.get("confidence", 0.8),
        payload=payload,
        source_event_id=data.get("source_event_id"),
    )
