"""
Planning routes:
    POST /planning/generate           — hybrid pipeline → new plan v1
    POST /planning/{plan_id}/update   — human edit → new immutable version
    POST /planning/{plan_id}/approve  — validate + approve
    GET  /planning/{model_id}/latest  — fetch latest version
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from ai_service.schemas.machining_plan import (
    PlanningRequest,
    MachiningPlanResponse,
    PlanUpdateRequest,
    PlanApproveRequest,
    PlanUpdateResponse,
    PlanDiff,
)
from ai_service.services.planning_service import generate_plan
from ai_service.services.feedback_service import (
    apply_edit,
    approve_plan,
    get_latest_plan,
)

logger = logging.getLogger(__name__)

planning_router = APIRouter(prefix="/planning", tags=["planning"])


# ── Generate ──────────────────────────────────────────────────────────────────

@planning_router.post(
    "/generate",
    response_model=MachiningPlanResponse,
    summary="Generate versioned machining plan (hybrid pipeline)",
    description=(
        "Full hybrid planning pipeline: "
        "validates features → rule engine → optional LLM optimiser → "
        "plan validation → save as new version with approved=False."
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


# ── Update (human edit) ──────────────────────────────────────────────────────

@planning_router.post(
    "/{plan_id}/update",
    response_model=PlanUpdateResponse,
    summary="Submit human edit → creates new immutable plan version",
    description=(
        "Accepts an edited plan, computes a structured diff against the "
        "original, creates a new plan version (approved=False), and "
        "stores a PlanFeedback record for audit + ML training."
    ),
)
async def update_plan(
    plan_id: str,
    req: PlanUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> PlanUpdateResponse:
    logger.info("Plan update request: plan_id=%s by=%s", plan_id, req.edited_by)

    new_plan = await apply_edit(
        plan_id=plan_id,
        edited_plan_data=req.edited_plan,
        edited_by=req.edited_by,
        session=session,
    )

    # Build response from newly created plan
    plan_response = MachiningPlanResponse(**new_plan.plan_data)

    # Retrieve the feedback record we just created (last added to session)
    # The diff is embedded in the feedback record
    from ai_service.services.feedback_service import calculate_diff
    from ai_service.models import MachiningPlan

    original = await session.get(MachiningPlan, plan_id)
    diff_data = calculate_diff(original.plan_data, req.edited_plan)

    # Find the feedback_id — it was the last PlanFeedback added
    from sqlalchemy import select
    from ai_service.models import PlanFeedback

    fb_result = await session.execute(
        select(PlanFeedback.id)
        .where(PlanFeedback.new_plan_id == new_plan.id)
        .limit(1)
    )
    feedback_id = fb_result.scalar_one()

    return PlanUpdateResponse(
        plan=plan_response,
        diff=PlanDiff(**diff_data),
        feedback_id=feedback_id,
    )


# ── Approve ──────────────────────────────────────────────────────────────────

@planning_router.post(
    "/{plan_id}/approve",
    response_model=MachiningPlanResponse,
    summary="Validate and approve a plan for RFQ eligibility",
    description=(
        "Re-validates the plan, then sets approved=True with the "
        "approver's user ID and timestamp. Already-approved plans "
        "are rejected (409). Only approved plans are eligible for RFQ."
    ),
)
async def approve(
    plan_id: str,
    req: PlanApproveRequest,
    session: AsyncSession = Depends(get_session),
) -> MachiningPlanResponse:
    logger.info("Plan approve request: plan_id=%s by=%s", plan_id, req.approved_by)

    plan = await approve_plan(
        plan_id=plan_id,
        approved_by=req.approved_by,
        session=session,
    )

    response = MachiningPlanResponse(**plan.plan_data)
    # Overlay approval fields (plan_data JSON may not have them yet)
    response.approved = True
    response.approved_by = plan.approved_by
    response.approved_at = plan.approved_at.isoformat() if plan.approved_at else None
    return response


# ── Latest ────────────────────────────────────────────────────────────────────

@planning_router.get(
    "/{model_id}/latest",
    response_model=MachiningPlanResponse,
    summary="Get the latest plan version for a model",
    description=(
        "Returns the highest-version plan for the given model_id, "
        "regardless of approval status."
    ),
)
async def latest(
    model_id: str,
    session: AsyncSession = Depends(get_session),
) -> MachiningPlanResponse:
    logger.info("Latest plan request: model_id=%s", model_id)

    plan = await get_latest_plan(model_id=model_id, session=session)

    response = MachiningPlanResponse(**plan.plan_data)
    response.approved = plan.approved
    response.approved_by = plan.approved_by
    response.approved_at = plan.approved_at.isoformat() if plan.approved_at else None
    return response
