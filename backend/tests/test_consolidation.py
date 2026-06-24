"""Consolidation math: P&L sign convention and elimination summary."""
from decimal import Decimal

from app.services.consolidation import _pnl_amount, _summarize


def test_pnl_sign_convention():
    # revenue is credit-positive, expense is debit-positive
    assert _pnl_amount("revenue", Decimal("0"), Decimal("100")) == Decimal("100")
    assert _pnl_amount("expense", Decimal("100"), Decimal("0")) == Decimal("100")
    assert _pnl_amount("asset", Decimal("100"), Decimal("0")) == Decimal("0")


def test_summarize_net_income():
    rows = [
        {"type": "revenue", "amount": Decimal("1000")},
        {"type": "expense", "amount": Decimal("400")},
    ]
    s = _summarize(rows)
    assert s["revenue"] == 1000.0
    assert s["expense"] == 400.0
    assert s["net_income"] == 600.0
