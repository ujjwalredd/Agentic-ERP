"""Auth: JWT minting/validation, role gating, and mode fallbacks. Pure (no DB)."""
import pytest
from fastapi import HTTPException

from app.config import settings
from app import security


def test_password_hash_roundtrip():
    h = security.hash_password("demo1234")
    assert h != "demo1234"
    assert security.verify_password("demo1234", h)
    assert not security.verify_password("wrong", h)


def test_jwt_mode_resolves_identity_and_role(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-secret")
    token = security.create_token("alice@demo", "controller")
    p = security._resolve(f"Bearer {token}")
    assert p.email == "alice@demo" and p.role == "controller"


def test_jwt_missing_and_invalid_token(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-secret")
    with pytest.raises(HTTPException) as e1:
        security._resolve(None)
    assert e1.value.status_code == 401
    with pytest.raises(HTTPException) as e2:
        security._resolve("Bearer not-a-jwt")
    assert e2.value.status_code == 403


def test_jwt_expired_token(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-secret")
    monkeypatch.setattr(settings, "jwt_expire_minutes", -1)  # already expired
    token = security.create_token("bob@demo", "viewer")
    with pytest.raises(HTTPException) as e:
        security._resolve(f"Bearer {token}")
    assert e.value.status_code == 401


def test_require_role_blocks_viewer(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "test-secret")
    viewer = security.create_token("v@demo", "viewer")
    dep = security.require_role("controller")
    with pytest.raises(HTTPException) as e:
        dep(authorization=f"Bearer {viewer}")
    assert e.value.status_code == 403
    # a controller passes and gets their email back
    ctrl = security.create_token("c@demo", "controller")
    assert dep(authorization=f"Bearer {ctrl}") == "c@demo"


def test_open_dev_mode_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "")
    monkeypatch.setattr(settings, "api_token", "")
    p = security._resolve(None)
    assert p.email == "demo-user" and p.role == "controller"


def test_shared_token_mode(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "")
    monkeypatch.setattr(settings, "api_token", "s3cret")
    monkeypatch.setattr(settings, "api_user", "ctrl@demo")
    assert security._resolve("Bearer s3cret").email == "ctrl@demo"
    with pytest.raises(HTTPException):
        security._resolve("Bearer wrong")
