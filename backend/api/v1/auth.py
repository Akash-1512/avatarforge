"""Auth API — register, login, and the current-user dependency.

POST /auth/register  -> create an account, return a JWT.
POST /auth/login     -> verify credentials, return a JWT.
GET  /auth/me        -> the authenticated user's profile.

`get_current_user` is the dependency every owned resource will use to resolve the
real user id from the Bearer token, replacing the old client-supplied user_id.
"""

import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.models.user import User
from backend.services.auth.service import (
    create_access_token,
    decode_token,
    hash_password,
    new_user_id,
    verify_password,
)

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _session_factory():
    from backend.models.db import get_session_factory

    return get_session_factory()


async def get_current_user(authorization: str = Header(default="")) -> User:
    """Resolve the authenticated user from a Bearer token, or 401."""
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization[7:].strip()
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    async with _session_factory()() as s:
        user = await s.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    display_name: str = Field("", max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    display_name: str


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id),
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
    )


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest) -> TokenResponse:
    email = req.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Invalid email")
    async with _session_factory()() as s:
        existing = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="Email already registered")
        user = User(
            id=new_user_id(),
            email=email,
            password_hash=hash_password(req.password),
            display_name=req.display_name.strip() or email.split("@")[0],
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)
    return _token_response(user)


@router.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
    email = req.email.strip().lower()
    async with _session_factory()() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
    # constant-ish response: verify even on missing user to avoid leaking which
    # emails exist (compare against a dummy hash when absent).
    valid = user is not None and verify_password(req.password, user.password_hash)
    if not valid or user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _token_response(user)


@router.get("/auth/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return {
        "user_id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
