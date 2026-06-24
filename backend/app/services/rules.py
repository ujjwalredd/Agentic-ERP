"""Rules engine — the explicit, codified accounting knowledge.

Deterministic vendor/regex matching (no LLM, so no hallucination). Rules are
created manually or learned from human corrections/approvals, turning tacit
"how this controller books things" into reusable, auditable logic.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Account, Correction, Rule


def _matches(rule: Rule, description: str) -> bool:
    text = description.lower()
    if rule.match_type == "regex":
        try:
            return re.search(rule.pattern, description, re.IGNORECASE) is not None
        except re.error:
            return False
    return rule.pattern.lower() in text  # vendor_contains (default)


def match(db: Session, entity_id: int, description: str) -> Rule | None:
    """First matching rule for this entity, then any global rule. Entity-specific
    rules win over global ones."""
    rules = list(
        db.scalars(
            select(Rule)
            .where((Rule.entity_id == entity_id) | (Rule.entity_id.is_(None)))
            .order_by(Rule.entity_id.is_(None))  # entity-specific (False) sorts first
        )
    )
    for rule in rules:
        if _matches(rule, description):
            return rule
    return None


def bump_hits(db: Session, rule: Rule) -> None:
    rule.hits = (rule.hits or 0) + 1
    db.flush()


def _account_name(db: Session, entity_id: int, code: str) -> str:
    acct = db.scalar(
        select(Account).where(Account.entity_id == entity_id, Account.code == code)
    )
    return acct.name if acct else code


def learn_from_correction(db: Session, correction: Correction) -> Rule | None:
    """Create a vendor rule from a human edit. The vendor token is derived from the
    transaction description; the account from what the human corrected it to."""
    after = correction.after or {}
    code = after.get("account_code")
    desc = after.get("description") or after.get("vendor")
    entity_id = after.get("entity_id")
    if not (code and desc and entity_id):
        return None
    # Use the first token of the description as the vendor signature (e.g. "AWS").
    pattern = str(desc).split()[0]
    return upsert(
        db,
        entity_id=entity_id,
        pattern=pattern,
        account_code=code,
        source="correction",
        created_by=correction.user_id,
    )


def upsert(
    db: Session,
    *,
    entity_id: int | None,
    pattern: str,
    account_code: str,
    match_type: str = "vendor_contains",
    auto_approve: bool = False,
    min_confidence: float = 0.9,
    tags: dict | None = None,
    source: str = "manual",
    created_by: str = "demo-user",
) -> Rule:
    """Create a rule, or update the account if an identical pattern already exists."""
    existing = db.scalar(
        select(Rule).where(
            Rule.entity_id == entity_id,
            Rule.pattern == pattern,
            Rule.match_type == match_type,
        )
    )
    if existing:
        existing.account_code = account_code
        existing.auto_approve = auto_approve or existing.auto_approve
        db.flush()
        return existing
    rule = Rule(
        entity_id=entity_id,
        match_type=match_type,
        pattern=pattern,
        account_code=account_code,
        tags=tags or {},
        auto_approve=auto_approve,
        min_confidence=min_confidence,
        source=source,
        created_by=created_by,
    )
    db.add(rule)
    db.flush()
    return rule
