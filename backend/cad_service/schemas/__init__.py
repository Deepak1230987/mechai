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


# ── Geometry sub-schema ──────────────────────────────────────────────────────

class GeometryResponse(BaseModel):
    """Geometry metrics extracted by the CAD Worker."""
    bounding_box: dict
    volume: float
    surface_area: float
    planar_faces: int
    cylindrical_faces: int
    conical_faces: int
    spherical_faces: int
    feature_ready: bool

    model_config = {"from_attributes": True}


class FeatureResponse(BaseModel):
    """A single detected machining feature."""
    type: str
    dimensions: dict
    depth: float | None = None
    diameter: float | None = None
    axis: dict | None = None
    tolerance: float | None = None
    surface_finish: str | None = None
    confidence: float

    model_config = {"from_attributes": True}


# ── Intelligence Response ─────────────────────────────────────────────────────

class IntelligenceResponse(BaseModel):
    """
    Manufacturing intelligence for a CAD model.

    This is the API contract between CAD Service and AI Service.
    The manufacturing_geometry_report is the single source of truth
    for all downstream planning and analysis.
    """
    model_id: str
    intelligence_ready: bool
    manufacturing_geometry_report: dict

    model_config = {"from_attributes": True}


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
    intelligence_ready: bool = False
    geometry: GeometryResponse | None = None
    features: list[FeatureResponse] | None = None
    gltf_url: str | None = None

    model_config = {"from_attributes": True}


class ModelListResponse(BaseModel):
    models: list[ModelResponse]
    total: int


class ViewerUrlResponse(BaseModel):
    model_id: str
    gltf_url: str
    expires_in_seconds: int = 900
