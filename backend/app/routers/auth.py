"""Login + identity endpoints (per-user JWT auth)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import get_db
from app.db.models import User
from app.security import create_token, current_principal, verify_password, Principal

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    role: str


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    if not settings.jwt_secret:
        raise HTTPException(400, "JWT auth not configured (JWT_SECRET unset)")
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "invalid credentials")
    return TokenOut(
        access_token=create_token(user.email, user.role),
        email=user.email,
        role=user.role,
    )


@router.get("/me", response_model=dict)
def me(principal: Principal = Depends(current_principal)):
    return {"email": principal.email, "role": principal.role}
