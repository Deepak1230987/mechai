"""
Schemas for conversational plan refinement (chat endpoint).

POST /planning/{plan_id}/chat  uses ChatRequest / ChatResponse.
"""

from __future__ import annotations

from typing import Literal
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
    """Result of a chat request, either a conversational message, a plan update, or a proposed plan update."""
    
    type: Literal["conversation", "plan_update", "plan_proposal"] = Field(
        ...,
        description="Type of response: 'conversation' for general chat, 'plan_proposal' when a change is drafted, 'plan_update' when applied."
    )
    message: str | None = Field(
        default=None,
        description="Natural language response (used for conversation type)",
    )
    explanation: str | None = Field(
        default=None,
        description="Human-readable reasoning for the changes made (used for plan_update and plan_proposal types)",
    )
    machining_plan: MachiningPlanResponse | None = Field(
        default=None,
        description="New plan version created from the refinement (used for plan_update type)",
    )
    proposed_plan: MachiningPlanResponse | None = Field(
        default=None,
        description="Drafted plan proposed to the user (used for plan_proposal type)",
    )
    version: int | None = Field(
        default=None,
        ge=1,
        description="Version number of the newly created plan",
    )
