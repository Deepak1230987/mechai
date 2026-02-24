"""
JWT creation and verification utilities.
Used by Auth Service (issue) and API Gateway (verify).
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from pydantic import BaseModel

from shared.config import get_settings

settings = get_settings()


class TokenPayload(BaseModel):
    sub: str          # user id
    role: str         # USER | VENDOR | ADMIN
    exp: datetime


def create_access_token(user_id: str, role: str) -> str:
    """Create a signed JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": user_id,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> TokenPayload:
    """
    Decode and validate a JWT.
    Raises JWTError on invalid / expired tokens.
    """
    try:
        data = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return TokenPayload(**data)
    except JWTError:
        raise
