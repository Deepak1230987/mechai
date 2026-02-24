"""
CAD Service routes.

All endpoints expect user identity injected by the API Gateway
via X-User-ID and X-User-Role headers.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from cad_service.schemas import (
    UploadRequest,
    UploadResponse,
    ConfirmUploadRequest,
    ModelResponse,
    ModelListResponse,
    ViewerUrlResponse,
)
from cad_service.services import (
    request_upload,
    confirm_upload,
    list_user_models,
    get_model,
    get_viewer_url,
)

models_router = APIRouter()


def _require_user_id(x_user_id: str | None = Header(None)) -> str:
    """Extract user ID from gateway-injected header."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-ID header (gateway must inject it)",
        )
    return x_user_id


@models_router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_model(
    payload: UploadRequest,
    user_id: str = Depends(_require_user_id),
    db: AsyncSession = Depends(get_session),
):
    """Request a signed upload URL for a CAD file."""
    return await request_upload(user_id, payload, db)


@models_router.post("/confirm-upload", response_model=ModelResponse)
async def confirm_model_upload(
    payload: ConfirmUploadRequest,
    user_id: str = Depends(_require_user_id),
    db: AsyncSession = Depends(get_session),
):
    """Confirm client-side upload is complete; triggers processing."""
    return await confirm_upload(user_id, payload, db)


@models_router.get("/", response_model=ModelListResponse)
async def list_models(
    skip: int = 0,
    limit: int = 50,
    user_id: str = Depends(_require_user_id),
    db: AsyncSession = Depends(get_session),
):
    """List the current user's models."""
    return await list_user_models(user_id, db, skip=skip, limit=limit)


@models_router.get("/{model_id}", response_model=ModelResponse)
async def get_single_model(
    model_id: str,
    user_id: str = Depends(_require_user_id),
    db: AsyncSession = Depends(get_session),
):
    """Get a single model detail with ownership check."""
    return await get_model(model_id, user_id, db)


@models_router.get("/{model_id}/viewer", response_model=ViewerUrlResponse)
async def get_model_viewer_url(
    model_id: str,
    user_id: str = Depends(_require_user_id),
    db: AsyncSession = Depends(get_session),
):
    """Get a signed glTF URL for the 3D viewer (only if status == READY)."""
    return await get_viewer_url(model_id, user_id, db)
