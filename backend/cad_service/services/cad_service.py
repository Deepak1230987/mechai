"""
CAD Service business logic.

Handles model metadata, signed URL generation, upload confirmation,
Pub/Sub event publishing, and viewer URL generation.

Does NOT contain:
  - Authentication logic (handled by gateway / auth service)
  - Feature recognition (handled by CAD Worker)
  - AI planning (future AI Service)
"""

import uuid
import json
import logging
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import get_settings
from cad_service.models import CADModel
from cad_service.schemas import (
    UploadRequest,
    UploadResponse,
    ConfirmUploadRequest,
    ModelResponse,
    ModelListResponse,
    ViewerUrlResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Allowed file formats ──────────────────────────────────────────────────────
ALLOWED_FORMATS = {"STEP", "IGES", "STL", "PARASOLID"}


# ── GCS helpers (abstracted for future extraction) ───────────────────────────

def _generate_signed_upload_url(gcs_path: str) -> str:
    """
    Generate a signed upload URL for GCS.

    In production, use google.cloud.storage.Client to generate a real signed URL.
    For local development, return a placeholder URL.
    """
    if settings.ENV == "production":
        # Production implementation would use:
        # from google.cloud import storage
        # client = storage.Client(project=settings.GCP_PROJECT_ID)
        # bucket = client.bucket(settings.GCS_BUCKET_NAME)
        # blob = bucket.blob(gcs_path)
        # url = blob.generate_signed_url(
        #     version="v4",
        #     expiration=timedelta(minutes=15),
        #     method="PUT",
        #     content_type="application/octet-stream",
        # )
        # return url
        raise NotImplementedError("Production GCS not configured yet")

    # Dev placeholder — in dev mode, the frontend can POST the file to a local endpoint
    return f"http://localhost:8002/dev/upload/{gcs_path}"


def _generate_signed_read_url(gcs_path: str) -> str:
    """
    Generate a signed read URL for serving glTF files.
    15-minute expiry.
    """
    if settings.ENV == "production":
        raise NotImplementedError("Production GCS not configured yet")

    return f"http://localhost:8002/dev/files/{gcs_path}"


async def _publish_processing_event(model_id: str, gcs_path: str) -> None:
    """
    Publish a Pub/Sub message to trigger the CAD Worker.

    In production, use google.cloud.pubsub_v1.PublisherClient.
    For local development, log the message (worker can poll DB or use a local queue).
    """
    message = {
        "model_id": model_id,
        "gcs_path": gcs_path,
        "action": "process_cad",
    }

    if settings.ENV == "production":
        # from google.cloud import pubsub_v1
        # publisher = pubsub_v1.PublisherClient()
        # topic_path = publisher.topic_path(settings.GCP_PROJECT_ID, settings.PUBSUB_TOPIC)
        # publisher.publish(topic_path, json.dumps(message).encode("utf-8"))
        raise NotImplementedError("Production Pub/Sub not configured yet")

    # Dev: just log it — the CAD Worker watches the DB in dev mode
    logger.info(f"[DEV] Pub/Sub event published: {json.dumps(message)}")


# ── Service functions ─────────────────────────────────────────────────────────

async def request_upload(
    user_id: str,
    payload: UploadRequest,
    db: AsyncSession,
) -> UploadResponse:
    """Create a model record and return a signed upload URL."""

    file_format = payload.file_format.upper()
    if file_format not in ALLOWED_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported format. Allowed: {', '.join(ALLOWED_FORMATS)}",
        )

    model_id = str(uuid.uuid4())
    gcs_path = f"uploads/{user_id}/{model_id}/{payload.filename}"

    model = CADModel(
        id=model_id,
        user_id=user_id,
        name=payload.name or payload.filename,
        original_filename=payload.filename,
        file_format=file_format,
        gcs_path=gcs_path,
        status="UPLOADED",
    )
    db.add(model)
    await db.flush()

    signed_url = _generate_signed_upload_url(gcs_path)

    return UploadResponse(
        model_id=model_id,
        signed_url=signed_url,
        gcs_path=gcs_path,
    )


async def confirm_upload(
    user_id: str,
    payload: ConfirmUploadRequest,
    db: AsyncSession,
) -> ModelResponse:
    """
    Confirm that the frontend finished uploading.
    Moves status to PROCESSING and publishes Pub/Sub event.
    """

    result = await db.execute(
        select(CADModel).where(CADModel.id == payload.model_id)
    )
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not the owner of this model")
    if model.status != "UPLOADED":
        raise HTTPException(status_code=409, detail="Model already confirmed or processing")

    model.status = "PROCESSING"
    await db.flush()
    await db.refresh(model)

    # Fire-and-forget Pub/Sub event to trigger the worker
    await _publish_processing_event(model.id, model.gcs_path)

    return ModelResponse.model_validate(model)


async def list_user_models(
    user_id: str,
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> ModelListResponse:
    """List models owned by a user."""

    count_result = await db.execute(
        select(func.count()).select_from(CADModel).where(CADModel.user_id == user_id)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(CADModel)
        .where(CADModel.user_id == user_id)
        .order_by(CADModel.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    models = result.scalars().all()

    return ModelListResponse(
        models=[ModelResponse.model_validate(m) for m in models],
        total=total,
    )


async def get_model(
    model_id: str,
    user_id: str,
    db: AsyncSession,
) -> ModelResponse:
    """Fetch a single model with ownership check."""

    result = await db.execute(
        select(CADModel).where(CADModel.id == model_id)
    )
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.user_id != user_id and model.visibility != "PUBLIC":
        raise HTTPException(status_code=403, detail="Access denied")

    return ModelResponse.model_validate(model)


async def get_viewer_url(
    model_id: str,
    user_id: str,
    db: AsyncSession,
) -> ViewerUrlResponse:
    """
    Return a signed glTF read URL if the model is READY.
    Per architecture: 15-minute expiry signed URL.
    """

    result = await db.execute(
        select(CADModel).where(CADModel.id == model_id)
    )
    model = result.scalar_one_or_none()

    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    if model.user_id != user_id and model.visibility != "PUBLIC":
        raise HTTPException(status_code=403, detail="Access denied")
    if model.status != "READY":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Model is not ready. Current status: {model.status}",
        )
    if not model.gltf_path:
        raise HTTPException(status_code=500, detail="glTF path missing despite READY status")

    gltf_url = _generate_signed_read_url(model.gltf_path)

    return ViewerUrlResponse(
        model_id=model.id,
        gltf_url=gltf_url,
    )
