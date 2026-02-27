"""
Planning routes:
    POST /planning/generate           — hybrid pipeline → new plan v1
    POST /planning/{plan_id}/update   — human edit → new immutable version
    POST /planning/{plan_id}/approve  — validate + approve
    POST /planning/{plan_id}/chat     — conversational refinement
    POST /planning/{plan_id}/narrative — generate process narrative
    POST /planning/{plan_id}/export   — PDF export
    GET  /planning/{model_id}/latest  — fetch latest version
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from ai_service.schemas.machining_plan import (
    PlanningRequest,
    MachiningPlanResponse,
    PlanUpdateRequest,
    PlanApproveRequest,
    PlanUpdateResponse,
    PlanDiff,
    VersionSummary,
)
from ai_service.schemas.chat_message import ChatRequest, ChatResponse
from ai_service.schemas.process_document import (
    NarrativeRequest,
    NarrativeResponse,
    ExportRequest,
)
from ai_service.services.planning_service import generate_plan
from ai_service.services.feedback_service import (
    apply_edit,
    approve_plan,
    get_latest_plan,
)
from ai_service.services.chat_refinement_service import chat_refine_plan
from ai_service.services.narrative_service import generate_process_narrative
from ai_service.services.document_service import generate_plan_pdf

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
    plan_obj = await generate_plan(req, session)
    # generate_plan returns MachiningPlanResponse built from plan_data;
    # overlay the DB row id so the client can call /update and /approve.
    # plan_obj doesn't have it yet — get it from the DB.
    from sqlalchemy import select as sa_select
    from ai_service.models import MachiningPlan
    row = await session.execute(
        sa_select(MachiningPlan.id)
        .where(MachiningPlan.model_id == req.model_id)
        .order_by(MachiningPlan.version.desc())
        .limit(1)
    )
    plan_obj.plan_id = row.scalar_one()
    return plan_obj


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

    plan_response.plan_id = new_plan.id
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
    response.plan_id = plan.id
    # Overlay approval fields (plan_data JSON may not have them yet)
    response.approved = True
    response.approved_by = plan.approved_by
    response.approved_at = plan.approved_at.isoformat() if plan.approved_at else None
    return response

# ── Chat Refinement ───────────────────────────────────────────────────────────

@planning_router.post(
    "/{plan_id}/chat",
    response_model=ChatResponse,
    summary="Conversational plan refinement via LLM",
    description=(
        "Send a natural-language instruction to refine the plan. "
        "Creates a new immutable version (approved=False). "
        "Requires an LLM provider to be configured."
    ),
)
async def chat(
    plan_id: str,
    req: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    logger.info(
        "Chat refinement: plan_id=%s msg=%r",
        plan_id,
        req.user_message[:80],
    )

    result = await chat_refine_plan(
        plan_id=plan_id,
        user_message=req.user_message,
        session=session,
    )

    if result["type"] == "conversation":
        return ChatResponse(
            type="conversation",
            message=result["message"],
        )

    if result["type"] == "plan_proposal":
        proposed_plan = result["proposed_plan"]
        plan_response = MachiningPlanResponse(**proposed_plan.plan_data)
        plan_response.plan_id = proposed_plan.id
        
        return ChatResponse(
            type="plan_proposal",
            explanation=result["explanation"],
            proposed_plan=plan_response,
            version=result["new_version"],
        )

    # It's a plan_update (although currently we only return plan_proposal)
    new_plan = result["new_plan"]
    plan_response = MachiningPlanResponse(**new_plan.plan_data)
    plan_response.plan_id = new_plan.id

    return ChatResponse(
        type="plan_update",
        explanation=result["explanation"],
        machining_plan=plan_response,
        version=result["new_version"],
    )


# ── Narrative Generation ──────────────────────────────────────────────────────

@planning_router.post(
    "/{plan_id}/narrative",
    response_model=NarrativeResponse,
    summary="Generate manufacturing process narrative",
    description=(
        "Produces a professional narrative covering material prep, "
        "workholding, operation reasoning, tool rationale, safety, "
        "and post-processing. Stored in the plan's process_summary field."
    ),
)
async def narrative(
    plan_id: str,
    req: NarrativeRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> NarrativeResponse:
    from ai_service.models import MachiningPlan as MachiningPlanModel

    plan = await session.get(MachiningPlanModel, plan_id)
    if plan is None:
        from fastapi import HTTPException, status as http_status
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )

    logger.info("Narrative generation: plan_id=%s", plan_id)

    # Try to fetch geometry metadata for richer narrative
    geometry_metadata = None
    try:
        from sqlalchemy import select as sa_select
        from cad_worker.models import ModelGeometry
        geom_result = await session.execute(
            sa_select(ModelGeometry).where(
                ModelGeometry.model_id == plan.model_id
            )
        )
        geom = geom_result.scalars().first()
        if geom:
            geometry_metadata = {
                "volume": geom.volume,
                "surface_area": geom.surface_area,
                "bounding_box": geom.bounding_box or {},
            }
    except Exception:
        logger.debug("Could not fetch geometry metadata — narrative will use plan data only")

    text = await generate_process_narrative(
        plan=plan,
        geometry_metadata=geometry_metadata,
        session=session,
    )

    return NarrativeResponse(
        plan_id=plan_id,
        process_summary=text,
        version=plan.version,
    )


# ── PDF Export ────────────────────────────────────────────────────────────────

@planning_router.post(
    "/{plan_id}/export",
    summary="Export machining plan as professional PDF",
    description=(
        "Generates a PDF process planning sheet. "
        "Draft plans include a 'DRAFT - NOT APPROVED' watermark. "
        "Returns application/pdf."
    ),
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "PDF process planning sheet",
        }
    },
)
async def export_pdf(
    plan_id: str,
    req: ExportRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> Response:
    from ai_service.models import MachiningPlan as MachiningPlanModel

    plan = await session.get(MachiningPlanModel, plan_id)
    if plan is None:
        from fastapi import HTTPException, status as http_status
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )

    export_req = req or ExportRequest()

    # Resolve part name
    part_name = export_req.part_name
    if not part_name:
        try:
            from sqlalchemy import select as sa_select
            from cad_service.models.cad_model import CADModel
            model_result = await session.execute(
                sa_select(CADModel.name).where(CADModel.id == plan.model_id)
            )
            part_name = model_result.scalar_one_or_none() or "Unnamed Part"
        except Exception:
            part_name = "Unnamed Part"

    logger.info("PDF export: plan_id=%s part=%s", plan_id, part_name)

    pdf_bytes = generate_plan_pdf(
        plan_data=plan.plan_data,
        material=plan.material,
        machine_type=plan.machine_type,
        version=plan.version,
        approved=plan.approved,
        approved_by=plan.approved_by,
        approved_at=plan.approved_at,
        process_summary=plan.process_summary,
        company_name=export_req.company_name,
        part_name=part_name,
        include_narrative=export_req.include_narrative,
    )

    filename = f"process_plan_{part_name.replace(' ', '_')}_v{plan.version}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )

# ── Version History ───────────────────────────────────────────────────────────

@planning_router.get(
    "/{model_id}/versions",
    response_model=list[VersionSummary],
    summary="List all plan versions for a model",
    description=(
        "Returns lightweight summaries of every plan version for the "
        "given model_id, ordered newest-first. Used for the version picker UI."
    ),
)
async def list_versions(
    model_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[VersionSummary]:
    from sqlalchemy import select as sa_select
    from ai_service.models import MachiningPlan

    logger.info("List versions: model_id=%s", model_id)

    result = await session.execute(
        sa_select(MachiningPlan)
        .where(MachiningPlan.model_id == model_id)
        .order_by(MachiningPlan.version.desc())
    )
    plans = result.scalars().all()

    if not plans:
        from fastapi import HTTPException, status as http_status
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"No plans found for model {model_id}",
        )

    summaries = []
    for p in plans:
        op_count = len(p.plan_data.get("operations", []))
        summaries.append(VersionSummary(
            plan_id=p.id,
            version=p.version,
            approved=p.approved,
            approved_by=p.approved_by,
            created_at=p.created_at.isoformat() if p.created_at else "",
            estimated_time=p.estimated_time,
            operation_count=op_count,
        ))

    return summaries


@planning_router.get(
    "/{model_id}/version/{version_num}",
    response_model=MachiningPlanResponse,
    summary="Get a specific plan version for a model",
    description=(
        "Returns the full plan for a specific version number. "
        "Used when the user selects a previous version from the picker."
    ),
)
async def get_version(
    model_id: str,
    version_num: int,
    session: AsyncSession = Depends(get_session),
) -> MachiningPlanResponse:
    from sqlalchemy import select as sa_select
    from ai_service.models import MachiningPlan

    logger.info("Get version: model_id=%s version=%d", model_id, version_num)

    result = await session.execute(
        sa_select(MachiningPlan)
        .where(
            MachiningPlan.model_id == model_id,
            MachiningPlan.version == version_num,
        )
        .limit(1)
    )
    plan = result.scalars().first()

    if plan is None:
        from fastapi import HTTPException, status as http_status
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Version {version_num} not found for model {model_id}",
        )

    response = MachiningPlanResponse(**plan.plan_data)
    response.plan_id = plan.id
    response.approved = plan.approved
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
    response.plan_id = plan.id
    response.approved = plan.approved
    response.approved_by = plan.approved_by
    response.approved_at = plan.approved_at.isoformat() if plan.approved_at else None
    return response
