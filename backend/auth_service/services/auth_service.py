"""
Auth business logic — register, login, role check.
No CAD / AI / RFQ logic here.
"""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_service.models import User
from auth_service.schemas import RegisterRequest, LoginRequest, UserResponse, TokenResponse
from shared.security import hash_password, verify_password, create_access_token


async def register_user(payload: RegisterRequest, db: AsyncSession) -> TokenResponse:
    """Register a new user and return JWT."""

    # Check duplicate email
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Validate role
    if payload.role not in ("USER", "VENDOR", "ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid role. Must be USER, VENDOR, or ADMIN.",
        )

    user = User(
        email=payload.email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(user_id=user.id, role=user.role)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


async def login_user(payload: LoginRequest, db: AsyncSession) -> TokenResponse:
    """Authenticate user and return JWT."""

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user_id=user.id, role=user.role)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


async def get_user_by_id(user_id: str, db: AsyncSession) -> UserResponse:
    """Fetch a user by id — used by gateway /me endpoint."""

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse.model_validate(user)
