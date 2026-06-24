"""Authentication for state-changing endpoints.

Optional bearer-token gate. If `API_TOKEN` is unset the API runs in open dev mode
(returns the demo user). If set, mutating endpoints require `Authorization:
Bearer <token>` and the audit log records `API_USER` as the actor — the client
cannot spoof identity, which is essential for a trustworthy audit trail.
"""
from __future__ import annotations

import hmac

from fastapi import Header, HTTPException

from app.config import settings


def current_user(authorization: str | None = Header(default=None)) -> str:
    if not settings.api_token:
        return "demo-user"  # open dev mode
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    if not hmac.compare_digest(token, settings.api_token):
        raise HTTPException(403, "invalid token")
    return settings.api_user
