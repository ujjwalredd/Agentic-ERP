"""Rules engine matching + auto-approve gating (pure / lightweight)."""
import types

from app.config import settings
from app.db.models import Rule
from app.services import approvals, rules


def test_vendor_contains_match():
    r = Rule(entity_id=1, match_type="vendor_contains", pattern="AWS", account_code="5000")
    assert rules._matches(r, "AWS WEB SERVICES")
    assert not rules._matches(r, "NOTION LABS")


def test_regex_match_and_bad_pattern():
    r = Rule(entity_id=1, match_type="regex", pattern=r"^STRIPE", account_code="4000")
    assert rules._matches(r, "STRIPE PAYOUT")
    assert not rules._matches(r, "PAYPAL")
    bad = Rule(entity_id=1, match_type="regex", pattern="[", account_code="5000")
    assert rules._matches(bad, "anything") is False  # invalid regex never crashes


def _action(payload, confidence):
    return types.SimpleNamespace(payload=payload, confidence=confidence, status="pending")


def test_auto_approve_gating_negatives():
    # no rule provenance -> not eligible (returns None, never touches the DB)
    assert approvals.auto_approve_if_eligible(None, _action({"auto_approve": False}, 0.99)) is None
    # rule match but confidence below the floor -> not eligible
    low = _action({"auto_approve": True, "rule_id": 1}, 0.5)
    assert approvals.auto_approve_if_eligible(None, low) is None


def test_auto_approve_disabled_flag(monkeypatch):
    monkeypatch.setattr(settings, "auto_approve_enabled", False)
    elig = _action({"auto_approve": True, "rule_id": 1}, 0.99)
    assert approvals.auto_approve_if_eligible(None, elig) is None
