"""
Auth Service routes.
Handles: POST /auth/register, POST /auth/login, GET /auth/me
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from auth_service.schemas import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from auth_service.services import register_user, login_user, get_user_by_id

auth_router = APIRouter()


@auth_router.post("/register", response_model=TokenResponse, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_session)):
    """Register a new user account."""
    return await register_user(payload, db)


@auth_router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_session)):
    """Authenticate and receive JWT."""
    return await login_user(payload, db)


@auth_router.get("/me", response_model=UserResponse)
async def me(
    user_id: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    """
    Get current user profile.
    In gateway-proxied mode the user_id comes from X-User-ID header
    which the gateway injects after JWT verification.
    When called directly (dev), pass user_id as query param.
    """
    if not user_id:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return await get_user_by_id(user_id, db)
