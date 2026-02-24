"""
Pydantic request / response schemas for CAD Service.
"""

from datetime import datetime

from pydantic import BaseModel


# ── Requests ──────────────────────────────────────────────────────────────────

class UploadRequest(BaseModel):
    """Request a signed URL for uploading a CAD file."""
    filename: str
    file_format: str  # STEP | IGES | STL | Parasolid
    name: str | None = None


class ConfirmUploadRequest(BaseModel):
    """Confirm that the client finished uploading to GCS."""
    model_id: str


class UpdateVisibilityRequest(BaseModel):
    visibility: str  # PRIVATE | PUBLIC


# ── Responses ─────────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    model_id: str
    signed_url: str
    gcs_path: str


class ModelResponse(BaseModel):
    id: str
    user_id: str
    name: str
    original_filename: str
    file_format: str
    version: int
    status: str
    visibility: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelListResponse(BaseModel):
    models: list[ModelResponse]
    total: int


class ViewerUrlResponse(BaseModel):
    model_id: str
    gltf_url: str
    expires_in_seconds: int = 900
