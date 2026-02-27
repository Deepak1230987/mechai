"""
Schemas for process document / PDF export.

POST /planning/{plan_id}/export  uses ExportRequest / metadata.
POST /planning/{plan_id}/narrative  uses NarrativeResponse.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Narrative ─────────────────────────────────────────────────────────────────

class NarrativeRequest(BaseModel):
    """Optional overrides for narrative generation."""

    company_name: str = Field(
        "MechAI Manufacturing",
        description="Company name for document header",
    )
    part_name: str | None = Field(
        None,
        description="Part name override (defaults to model filename)",
    )


class NarrativeResponse(BaseModel):
    """Result of narrative generation."""

    plan_id: str
    process_summary: str = Field(
        ...,
        description="Full manufacturing narrative (markdown-formatted)",
    )
    version: int


# ── Export ────────────────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    """Parameters for PDF export."""

    company_name: str = Field(
        "MechAI Manufacturing",
        max_length=100,
        description="Company name in document header",
    )
    part_name: str | None = Field(
        None,
        max_length=200,
        description="Part name override",
    )
    include_narrative: bool = Field(
        True,
        description="Whether to include the process narrative section",
    )
