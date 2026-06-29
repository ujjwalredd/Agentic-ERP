"""Authentication + authorization for the API.

Three modes, in precedence order:

1. **Per-user JWT** (when `JWT_SECRET` is set): mutating endpoints require a
   `Authorization: Bearer <jwt>` minted by `POST /auth/login`. The token carries
   the user's email + role; that email is what lands in the immutable AuditLog, so
   accountability is per-person. Roles gate writes (`controller` vs `viewer`).
2. **Shared API token** (when only `API_TOKEN` is set): legacy single-token gate;
   the audit actor is `API_USER`, role assumed `controller`.
3. **Open dev** (neither set): returns `demo-user`/`controller` — for local + mock
   runs and the existing integration tests, no setup required.
"""
from __future__ import annotations

import datetime as dt
import hmac
from dataclasses import dataclass

import jwt
from fastapi import Header, HTTPException
from passlib.context import CryptContext

from app.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd.verify(password, password_hash)


def create_token(email: str, role: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": email,
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


@dataclass
class Principal:
    email: str
    role: str


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    return authorization.split(" ", 1)[1]


def _resolve(authorization: str | None) -> Principal:
    # Mode 1: per-user JWT.
    if settings.jwt_secret:
        token = _bearer(authorization)
        try:
            claims = jwt.decode(
                token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(401, "token expired")
        except jwt.PyJWTError:
            raise HTTPException(403, "invalid token")
        return Principal(email=claims.get("sub", "unknown"), role=claims.get("role", "viewer"))

    # Mode 2: shared API token.
    if settings.api_token:
        token = _bearer(authorization)
        if not hmac.compare_digest(token, settings.api_token):
            raise HTTPException(403, "invalid token")
        return Principal(email=settings.api_user, role="controller")

    # Mode 3: open dev.
    return Principal(email="demo-user", role="controller")


def current_principal(authorization: str | None = Header(default=None)) -> Principal:
    return _resolve(authorization)


def current_user(authorization: str | None = Header(default=None)) -> str:
    """Backwards-compatible identity dependency (returns the actor email)."""
    return _resolve(authorization).email


def require_role(*roles: str):
    """Dependency factory: enforce that the caller has one of `roles`. Returns the
    actor email so handlers can stamp it into the audit log."""

    def _dep(authorization: str | None = Header(default=None)) -> str:
        principal = _resolve(authorization)
        if principal.role not in roles:
            raise HTTPException(
                403, f"role '{principal.role}' not permitted (requires {' or '.join(roles)})"
            )
        return principal.email

    return _dep
