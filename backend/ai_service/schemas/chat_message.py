"""
Schemas for conversational plan refinement (chat endpoint).

POST /planning/{plan_id}/chat  uses ChatRequest / ChatResponse.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ai_service.schemas.machining_plan import MachiningPlanResponse


# ── Request ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """User message for conversational plan refinement."""

    user_message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language instruction for plan modification",
    )


# ── Response ──────────────────────────────────────────────────────────────────

class ChatResponse(BaseModel):
    """Result of a chat-driven plan refinement."""

    explanation: str = Field(
        ...,
        description="Human-readable reasoning for the changes made",
    )
    machining_plan: MachiningPlanResponse = Field(
        ...,
        description="New plan version created from the refinement",
    )
    version: int = Field(
        ...,
        ge=1,
        description="Version number of the newly created plan",
    )
