"""
Intelligence Client — fetches ManufacturingGeometryReport from CAD Service.

The AI Service MUST NOT directly query CAD Worker DB tables.
All intelligence data flows through the CAD Service API:

    CAD Worker → DB → CAD Service API → AI Service

This ensures:
  • Single source of truth (ManufacturingGeometryReport JSONB)
  • Service boundary enforcement
  • Intelligence availability is validated at query time
"""

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel, Field, ValidationError

from shared.config import get_settings

logger = logging.getLogger("ai_service.ingestion.intelligence_client")
settings = get_settings()

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Lazy-initialize the httpx async client."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


# ── Pydantic validation model for the response ───────────────────────────────

class IntelligencePayload(BaseModel):
    """Validates the raw CAD Service intelligence response."""

    model_id: str
    intelligence_ready: bool
    manufacturing_geometry_report: dict = Field(
        ..., description="Full ManufacturingGeometryReport as dict"
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def fetch_model_intelligence(model_id: str) -> IntelligencePayload:
    """
    Fetch the ManufacturingGeometryReport from CAD Service.

    Calls: GET {CAD_SERVICE_URL}/models/{model_id}/intelligence

    Returns:
        Pydantic-validated IntelligencePayload.

    Raises:
        ValueError: If intelligence is not available or response is invalid.
    """
    url = f"{settings.CAD_SERVICE_URL}/models/{model_id}/intelligence"
    logger.info("Fetching intelligence for model %s from %s", model_id, url)

    client = _get_client()

    try:
        response = await client.get(url)
    except httpx.RequestError as exc:
        logger.error("Failed to reach CAD Service for model %s: %s", model_id, exc)
        raise ValueError(f"Cannot reach CAD Service: {exc}") from exc

    if response.status_code == 404:
        detail = response.json().get("detail", "Intelligence not available")
        logger.warning("Intelligence not found for model %s: %s", model_id, detail)
        raise ValueError(detail)

    if response.status_code != 200:
        logger.error(
            "CAD Service returned %d for model %s: %s",
            response.status_code, model_id, response.text[:500],
        )
        raise ValueError(
            f"CAD Service returned status {response.status_code}"
        )

    # Pydantic validation
    try:
        payload = IntelligencePayload(**response.json())
    except ValidationError as exc:
        logger.error("Invalid intelligence payload for model %s: %s", model_id, exc)
        raise ValueError(f"Invalid intelligence response: {exc}") from exc

    if not payload.intelligence_ready:
        raise ValueError(
            f"Intelligence not yet ready for model {model_id}"
        )

    feature_count = len(payload.manufacturing_geometry_report.get("features", []))
    logger.info(
        "Intelligence fetched: model=%s features=%d",
        model_id, feature_count,
    )
    return payload
