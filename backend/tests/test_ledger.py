"""Double-entry accuracy: an entry must balance to the cent or it is rejected."""
import pytest

from app.services.ledger import UnbalancedEntryError, _validate_balanced


def test_balanced_entry_passes():
    _validate_balanced([{"debit": 100}, {"credit": 100}])


def test_split_lines_balance():
    _validate_balanced([{"debit": 60}, {"debit": 40}, {"credit": 100}])


def test_unbalanced_raises():
    with pytest.raises(UnbalancedEntryError):
        _validate_balanced([{"debit": 100}, {"credit": 99.99}])


def test_zero_total_raises():
    with pytest.raises(UnbalancedEntryError):
        _validate_balanced([{"debit": 0}, {"credit": 0}])
