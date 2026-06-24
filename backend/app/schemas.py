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
