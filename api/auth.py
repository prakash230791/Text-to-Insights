"""
API Gateway — JWT Authentication  (api/auth.py)

Pure-stdlib HS256 JWT + PBKDF2 password hashing.
No external cryptography package required.

Provides:
  • create_access_token()  — sign a JWT for a user
  • get_current_user()     — FastAPI dependency for protected routes
  • /auth/token endpoint   — password exchange for JWT
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from config.settings import get_settings

cfg = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
router = APIRouter(prefix="/auth", tags=["auth"])

_SALT = b"tti-demo-salt-2024"  # fixed salt fine for demo; use random per-user in prod


# ── Minimal HS256 JWT (stdlib only) ───────────────────────────────────────────

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


def _jwt_encode(payload: dict, secret: str) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url(json.dumps(payload).encode())
    sig = _b64url(
        hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{body}.{sig}"


def _jwt_decode(token: str, secret: str) -> dict:
    try:
        header, body, sig = token.split(".")
    except ValueError:
        raise ValueError("Malformed token")
    expected_sig = _b64url(
        hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(sig, expected_sig):
        raise ValueError("Invalid signature")
    payload = json.loads(_b64url_decode(body))
    if payload.get("exp", 0) < time.time():
        raise ValueError("Token expired")
    return payload


# ── Password hashing (PBKDF2-SHA256) ──────────────────────────────────────────

def _hash_password(password: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), _SALT, 260_000)
    return dk.hex()


def _verify_password(password: str, hashed: str) -> bool:
    return hmac.compare_digest(_hash_password(password), hashed)


# ── Demo user store — replace with your real user DB ─────────────────────────

_DEMO_USERS: dict[str, dict] = {
    "analyst": {"user_id": "analyst", "hashed_password": _hash_password("analyst123"), "role": "analyst"},
    "admin":   {"user_id": "admin",   "hashed_password": _hash_password("admin123"),   "role": "admin"},
}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserContext(BaseModel):
    user_id: str
    role: str


# ── Token creation ─────────────────────────────────────────────────────────────

def create_access_token(user_id: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": int(time.time()) + cfg.jwt_access_token_expire_minutes * 60,
        "iat": int(time.time()),
    }
    return _jwt_encode(payload, cfg.jwt_secret_key)


# ── FastAPI dependency ─────────────────────────────────────────────────────────

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserContext:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = _jwt_decode(token, cfg.jwt_secret_key)
        user_id: str = payload.get("sub", "")
        role: str = payload.get("role", "analyst")
        if not user_id:
            raise credentials_exc
    except ValueError:
        raise credentials_exc
    return UserContext(user_id=user_id, role=role)


def require_admin(user: Annotated[UserContext, Depends(get_current_user)]) -> UserContext:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


# ── Auth route ─────────────────────────────────────────────────────────────────

@router.post("/token", response_model=TokenResponse)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> TokenResponse:
    user_rec = _DEMO_USERS.get(form.username)
    if not user_rec or not _verify_password(form.password, user_rec["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user_rec["user_id"], user_rec["role"])
    return TokenResponse(
        access_token=token,
        expires_in=cfg.jwt_access_token_expire_minutes * 60,
    )
