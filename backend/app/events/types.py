from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict

# Event types the Orchestrator routes on.
BANK_LINE = "bank.line"          # raw bank/credit feed line  -> Categorizer/Reconciler
INVOICE_RECEIVED = "invoice.received"  # vendor invoice/bill    -> Bill Handler
AR_OVERDUE = "ar.overdue"        # customer invoice overdue    -> AR Clerk
INTERCOMPANY = "intercompany.detected"  # cross-entity pair     -> Consolidator
CLOSE_TRIGGER = "close.trigger"  # month-end close kickoff      -> Closer
ENTRY_POSTED = "entry.posted"    # a draft was approved+posted  -> Consolidator/recompute


@dataclass
class Event:
    type: str
    data: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(type=d["type"], data=d.get("data", {}), id=d.get("id", uuid.uuid4().hex))
