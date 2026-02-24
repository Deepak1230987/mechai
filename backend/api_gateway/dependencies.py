"""
JWT verification dependency for the API Gateway.

Extracts and validates the Bearer token, then provides
user_id and user_role that get forwarded to internal services
as X-User-ID and X-User-Role headers.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from shared.security import decode_access_token, TokenPayload

_bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    """Lightweight container for the authenticated user context."""
    def __init__(self, user_id: str, role: str):
        self.user_id = user_id
        self.role = role


async def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """
    Dependency that enforces JWT authentication.
    Returns CurrentUser with user_id and role.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload: TokenPayload = decode_access_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(user_id=payload.sub, role=payload.role)


async def optional_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser | None:
    """
    Dependency that optionally extracts user context.
    Returns None if no token is present (public routes).
    """
    if not credentials:
        return None

    try:
        payload: TokenPayload = decode_access_token(credentials.credentials)
        return CurrentUser(user_id=payload.sub, role=payload.role)
    except JWTError:
        return None
