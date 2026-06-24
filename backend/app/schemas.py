from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class ApproveRequest(BaseModel):
    user_id: str = "demo-user"


class ProposedActionOut(BaseModel):
    id: int
    agent: str
    action_type: str
    summary: str
    confidence: float
    payload: dict
    status: str
    source_event_id: str | None = None
    created_at: dt.datetime

    class Config:
        from_attributes = True


class AuditLogOut(BaseModel):
    id: int
    timestamp: dt.datetime
    user_id: str
    agent: str
    action: str
    proposed_action_id: int
    before: dict
    after: dict

    class Config:
        from_attributes = True


class SimulateRequest(BaseModel):
    kind: str  # bank_feed | invoice | bill | intercompany | close


class RejectRequest(BaseModel):
    reason: str = ""


class EditRequest(BaseModel):
    """Human correction of a draft before approval."""
    account_code: str | None = None  # re-categorize to this GL account
    reason: str = ""
    create_rule: bool = False        # codify this correction as a reusable rule
    auto_approve: bool = False       # if creating a rule, make it auto-approving


class RuleIn(BaseModel):
    entity_id: int | None = None     # null = applies to all entities
    match_type: str = "vendor_contains"  # | regex
    pattern: str
    account_code: str
    auto_approve: bool = False
    min_confidence: float = 0.9


class RuleOut(BaseModel):
    id: int
    entity_id: int | None
    match_type: str
    pattern: str
    account_code: str
    auto_approve: bool
    min_confidence: float
    source: str
    hits: int
    created_by: str

    class Config:
        from_attributes = True
