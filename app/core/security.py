# app/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_ctx = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")
ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


def _create_token(sub: str, expires_delta: timedelta, token_type: str) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, s.SECRET_KEY, algorithm=s.JWT_ALG)


def create_access_token(user_id: str) -> str:
    s = get_settings()
    return _create_token(user_id, timedelta(minutes=s.ACCESS_EXPIRE_MIN), "access")


def create_refresh_token(user_id: str) -> str:
    s = get_settings()
    return _create_token(user_id, timedelta(days=s.REFRESH_EXPIRE_DAYS), "refresh")


def decode_token(token: str) -> Optional[dict[str, Any]]:
    s = get_settings()
    try:
        return jwt.decode(token, s.SECRET_KEY, algorithms=[s.JWT_ALG])
    except JWTError:
        return None
