"""
API Gateway — JWT Authentication  (api/auth.py)

Provides:
  • create_access_token()  — sign a JWT for a user
  • get_current_user()     — FastAPI dependency for protected routes
  • /auth/token endpoint   — password exchange for JWT
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from config.settings import get_settings

cfg = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Demo user store — replace with your real user DB ─────────────────────────

_DEMO_USERS: dict[str, dict] = {
    "analyst": {
        "user_id": "analyst",
        "hashed_password": _pwd_context.hash("analyst123"),
        "role": "analyst",
    },
    "admin": {
        "user_id": "admin",
        "hashed_password": _pwd_context.hash("admin123"),
        "role": "admin",
    },
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
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=cfg.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, cfg.jwt_secret_key, algorithm=cfg.jwt_algorithm)


# ── FastAPI dependency ─────────────────────────────────────────────────────────

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserContext:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, cfg.jwt_secret_key, algorithms=[cfg.jwt_algorithm])
        user_id: str = payload.get("sub", "")
        role: str = payload.get("role", "analyst")
        if not user_id:
            raise credentials_exc
    except JWTError:
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
    if not user_rec or not _pwd_context.verify(form.password, user_rec["hashed_password"]):
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
