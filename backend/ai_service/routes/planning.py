"""
Planning route — POST /planning/generate

Receives model_id + material + machine_type, runs the deterministic
rule engine, and returns a complete MachiningPlan.

No AI.  No LLM.  Pure rule-based.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from ai_service.schemas.machining_plan import PlanningRequest, MachiningPlanResponse
from ai_service.services.planning_service import generate_plan

logger = logging.getLogger(__name__)

planning_router = APIRouter(prefix="/planning", tags=["planning"])


@planning_router.post(
    "/generate",
    response_model=MachiningPlanResponse,
    summary="Generate deterministic machining plan",
    description=(
        "Fetches features from DB for the given model, runs the rule engine, "
        "selects tools, estimates time, and returns a complete plan. "
        "No AI / LLM calls — purely deterministic."
    ),
)
async def generate(
    req: PlanningRequest,
    session: AsyncSession = Depends(get_session),
) -> MachiningPlanResponse:
    logger.info(
        "Planning request: model=%s material=%s machine=%s",
        req.model_id,
        req.material,
        req.machine_type,
    )
    return await generate_plan(req, session)
