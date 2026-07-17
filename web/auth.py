from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

import jwt
import bcrypt as _bcrypt

logger = logging.getLogger("hlb-git-pm.auth")

_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "hlb-git-pm-dev-secret-change-in-production")
_ALGORITHM = "HS256"
_EXPIRE_HOURS = 24


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
