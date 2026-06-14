"""Auth: password hashing, JWT, and the register/login/me flow."""

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.api.v1.auth as auth_api
from backend.main import create_app
from backend.models.db import Base
from backend.services.auth.service import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_is_salted_and_verifies():
    h1 = hash_password("correct horse battery")
    h2 = hash_password("correct horse battery")
    assert h1 != h2  # salted
    assert verify_password("correct horse battery", h1)
    assert not verify_password("wrong", h1)


def test_verify_handles_garbage_hash():
    assert verify_password("x", "not-a-bcrypt-hash") is False


def test_jwt_roundtrip_and_rejects_tampering():
    tok = create_access_token("user-123")
    assert decode_token(tok) == "user-123"
    assert decode_token(tok + "tamper") is None
    assert decode_token("totally.invalid") is None


@pytest_asyncio.fixture
async def api(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/auth.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(auth_api, "_session_factory", lambda: sf)
    yield TestClient(create_app())
    await engine.dispose()


def test_register_returns_token(api):
    r = api.post(
        "/api/v1/auth/register", json={"email": "Ada@Example.com", "password": "lovelace1843"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token_type"] == "bearer" and body["access_token"]
    assert body["email"] == "ada@example.com"  # normalized lowercase
    assert body["display_name"] == "ada"  # derived from email


def test_register_rejects_short_password(api):
    r = api.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "short"})
    assert r.status_code == 422


def test_register_rejects_duplicate(api):
    api.post("/api/v1/auth/register", json={"email": "dup@x.com", "password": "password123"})
    r = api.post("/api/v1/auth/register", json={"email": "dup@x.com", "password": "password123"})
    assert r.status_code == 409


def test_login_flow_and_bad_credentials(api):
    api.post("/api/v1/auth/register", json={"email": "kai@x.com", "password": "password123"})
    ok = api.post("/api/v1/auth/login", json={"email": "kai@x.com", "password": "password123"})
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = api.post("/api/v1/auth/login", json={"email": "kai@x.com", "password": "WRONG"})
    assert bad.status_code == 401
    missing = api.post(
        "/api/v1/auth/login", json={"email": "nobody@x.com", "password": "password123"}
    )
    assert missing.status_code == 401  # same 401, no user-enumeration leak


def test_me_requires_valid_token(api):
    reg = api.post(
        "/api/v1/auth/register", json={"email": "me@x.com", "password": "password123"}
    ).json()
    token = reg["access_token"]
    ok = api.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200 and ok.json()["email"] == "me@x.com"
    assert api.get("/api/v1/auth/me").status_code == 401  # no header
    assert api.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401
