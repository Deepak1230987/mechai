"""
Alternative Generator — LLM suggests optional improvements.

Proposals:
  - Reduce setups (combine orientations)
  - Change material strategy (different stock form)
  - Change tolerance approach (adjust finishing passes)

Returns structured proposals, NEVER applied automatically.
User must explicitly accept via consent flow.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from ai_service.schemas.machining_plan import MachiningPlanResponse
from ai_service.schemas.planning_context import PlanningContext
from ai_service.services.langchain_pipeline import _build_llm

logger = logging.getLogger("ai_service.reasoning.alternative_generator")


# ── Schema for alternatives ──────────────────────────────────────────────────

class AlternativeProposal(BaseModel):
    """A single optional improvement suggestion."""

    id: str = Field(..., description="Unique proposal ID")
    category: str = Field(
        ..., description="SETUP_REDUCTION | MATERIAL_STRATEGY | TOLERANCE_APPROACH | TOOL_OPTIMIZATION"
    )
    title: str = Field(..., description="Short human-readable title")
    description: str = Field(..., description="Detailed explanation")
    estimated_impact: str = Field("", description="E.g. '-15% time', 'fewer setups'")
    risk_level: str = Field("LOW", description="LOW | MEDIUM | HIGH")
    affected_feature_ids: list[str] = Field(default_factory=list)


class AlternativesResponse(BaseModel):
    """Collection of alternative proposals."""

    proposals: list[AlternativeProposal] = Field(default_factory=list)
    generation_note: str = ""


# ── LLM Prompt ───────────────────────────────────────────────────────────────

_SYSTEM = """\
You are a manufacturing process consultant. Given a machining plan,
suggest optional improvements the engineer might consider.

Output a JSON object with this structure:
{{
  "proposals": [
    {{
      "id": "<unique-id>",
      "category": "SETUP_REDUCTION|MATERIAL_STRATEGY|TOLERANCE_APPROACH|TOOL_OPTIMIZATION",
      "title": "<short title>",
      "description": "<detailed explanation>",
      "estimated_impact": "<e.g. -15% time>",
      "risk_level": "LOW|MEDIUM|HIGH",
      "affected_feature_ids": ["<feature-id>"]
    }}
  ],
  "generation_note": "<brief note about the analysis>"
}}

RULES:
1. Only reference existing feature IDs.
2. Do NOT suggest changes already in the plan.
3. Each proposal must be independently applicable.
4. Maximum 5 proposals.
5. Output ONLY JSON.
"""

_USER = """\
Material: {material}, Machine: {machine_type}
Complexity: {complexity}, Setups: {num_setups}

Plan:
{plan_json}

Features:
{features_json}

Suggest improvements.
"""


async def generate_alternatives(
    plan: MachiningPlanResponse,
    context: PlanningContext,
) -> AlternativesResponse:
    """
    Generate optional improvement proposals using LLM.

    Returns AlternativesResponse (empty if LLM unavailable).
    """
    llm = _build_llm()
    if llm is None:
        return AlternativesResponse(
            generation_note="LLM unavailable — no alternatives generated"
        )

    try:
        return await _call_llm(llm, plan, context)
    except Exception:
        logger.exception("Alternative generation failed")
        return AlternativesResponse(
            generation_note="Alternative generation failed — LLM error"
        )


async def _call_llm(
    llm: Any,
    plan: MachiningPlanResponse,
    context: PlanningContext,
) -> AlternativesResponse:
    """Single LLM call for alternative generation."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM),
        ("human", _USER),
    ])
    parser = JsonOutputParser()
    chain = prompt | llm | parser

    result = await chain.ainvoke({
        "material": context.material,
        "machine_type": context.machine_type,
        "complexity": context.complexity_score,
        "num_setups": len(plan.setups),
        "plan_json": json.dumps(plan.model_dump(exclude={"plan_id"}), indent=2, default=str),
        "features_json": json.dumps(
            [f.model_dump() for f in context.features], indent=2, default=str
        ),
    })

    if not isinstance(result, dict):
        return AlternativesResponse(generation_note="LLM returned invalid format")

    try:
        response = AlternativesResponse(**result)
    except Exception as exc:
        logger.warning("Failed to parse alternatives: %s", exc)
        return AlternativesResponse(generation_note=f"Parse error: {exc}")

    logger.info(
        "Generated %d alternative proposals", len(response.proposals)
    )
    return response
