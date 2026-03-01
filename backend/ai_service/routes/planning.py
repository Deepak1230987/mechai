"""
Planning routes:
    POST /planning/generate           — hybrid pipeline → new plan v1
    POST /planning/{plan_id}/update   — human edit → new immutable version
    POST /planning/{plan_id}/approve  — validate + approve
    POST /planning/{plan_id}/chat     — conversational refinement
    POST /planning/{plan_id}/narrative — generate process narrative
    POST /planning/{plan_id}/export   — PDF export
    POST /planning/{model_id}/rollback — restore a previous version
    GET  /planning/{model_id}/latest  — fetch latest version
    GET  /planning/{model_id}/versions — version list
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
    RollbackRequest,
)
from ai_service.schemas.chat_message import ChatRequest, ChatResponse
from ai_service.schemas.process_document import (
    NarrativeRequest,
    NarrativeResponse,
    ExportRequest,
)
from ai_service.services.planning_service import generate_plan, rollback_plan
from ai_service.services.feedback_service import (
    apply_edit,
    approve_plan,
    get_latest_plan,
)
from ai_service.chat.intent_router import IntentRouter, IntentType
from ai_service.chat.refinement_engine import generate_refinement_diff
from ai_service.chat.consent_manager import ConsentManager
from ai_service.reasoning.narrative_generator import generate_narrative
from ai_service.reasoning.alternative_generator import generate_alternatives
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
        "validates features  → optional LLM optimiser → "
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
    from ai_service.models import MachiningPlan as MachiningPlanModel
    from ai_service.schemas.planning_context import PlanningContext, FeatureContext
    from ai_service.versioning.plan_version_service import PlanVersionService

    logger.info(
        "Chat refinement: plan_id=%s msg=%r",
        plan_id,
        req.user_message[:80],
    )

    # ── 1. Classify intent ───────────────────────────────────────────────
    router = IntentRouter()
    intent = router.classify_intent(req.user_message)

    # ── Handle confirm / reject ──────────────────────────────────────────
    if intent == IntentType.CONFIRM_CHANGE:
        confirmed_plan = ConsentManager.confirm(plan_id)
        if confirmed_plan is None:
            return ChatResponse(
                type="conversation",
                message="No pending proposal to confirm.",
            )
        version_svc = PlanVersionService(session)
        row = await version_svc.save_new_version(
            previous_plan_id=plan_id,
            plan=confirmed_plan,
            modification_reason="User confirmed chat proposal",
        )
        confirmed_plan.plan_id = row.id
        return ChatResponse(
            type="plan_update",
            explanation="Changes confirmed and saved as new version.",
            machining_plan=confirmed_plan,
            version=row.version,
        )

    if intent == IntentType.REJECT_CHANGE:
        ConsentManager.reject(plan_id)
        return ChatResponse(
            type="conversation",
            message="Proposed changes discarded. The plan remains unchanged.",
        )

    # ── Handle general conversation ──────────────────────────────────────
    if intent == "GENERAL_CONVERSATION":
        # Build a brief plan summary for context
        plan_row_conv = await session.get(MachiningPlanModel, plan_id)
        plan_summary = "No plan loaded."
        if plan_row_conv:
            pd = plan_row_conv.plan_data
            plan_summary = (
                f"Material: {plan_row_conv.material}, "
                f"Machine: {plan_row_conv.machine_type}, "
                f"Ops: {len(pd.get('operations', []))}, "
                f"Time: {pd.get('estimated_time', 0):.1f}s, "
                f"Version: {plan_row_conv.version}"
            )
        response_text = await router.conversational_response(
            req.user_message, plan_summary
        )
        return ChatResponse(
            type="conversation",
            message=response_text,
        )

    # ── Handle rollback ──────────────────────────────────────────────────
    if intent == "ROLLBACK":
        target_v = IntentRouter.parse_rollback_version(req.user_message)
        if target_v is None:
            return ChatResponse(
                type="conversation",
                message="I understood you want to roll back, but I couldn't determine "
                        "the target version. Please say something like "
                        "'rollback to version 2' or 'undo last change'.",
            )

        # Resolve plan_id → model_id
        rollback_plan_row = await session.get(MachiningPlanModel, plan_id)
        if rollback_plan_row is None:
            from fastapi import HTTPException, status as http_status
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Plan {plan_id} not found",
            )

        model_id = rollback_plan_row.model_id

        # Resolve -1 sentinel → previous version
        if target_v == -1:
            target_v = max(rollback_plan_row.version - 1, 1)

        try:
            restored = await rollback_plan(
                model_id=model_id,
                target_version=target_v,
                reason=f"Chat rollback: {req.user_message[:200]}",
                session=session,
            )
        except Exception as exc:
            return ChatResponse(
                type="conversation",
                message=f"Rollback failed: {exc}",
            )

        return ChatResponse(
            type="plan_update",
            explanation=f"Rolled back to version {target_v}. "
                        f"Created new version {restored.version} (rollback).",
            machining_plan=restored,
            version=restored.version,
        )

    # ── Handle request alternatives ──────────────────────────────────────
    if intent == "REQUEST_ALTERNATIVES":
        alt_plan_row = await session.get(MachiningPlanModel, plan_id)
        if alt_plan_row is None:
            from fastapi import HTTPException, status as http_status
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Plan {plan_id} not found",
            )

        alt_plan_response = MachiningPlanResponse(**alt_plan_row.plan_data)
        alt_plan_response.plan_id = alt_plan_row.id

        # Build PlanningContext from plan data
        alt_features = []
        alt_seen: set[str] = set()
        for op in alt_plan_row.plan_data.get("operations", []):
            fid = op.get("feature_id")
            if fid and fid not in alt_seen:
                alt_seen.add(fid)
                alt_features.append(
                    FeatureContext(id=fid, type="UNKNOWN", confidence=1.0)
                )
        alt_context = PlanningContext(
            model_id=alt_plan_row.model_id,
            material=alt_plan_row.material,
            machine_type=alt_plan_row.machine_type,
            features=alt_features,
        )

        alternatives = await generate_alternatives(alt_plan_response, alt_context)
        if not alternatives.proposals:
            return ChatResponse(
                type="conversation",
                message="No alternative suggestions at this time.",
            )

        # Format alternatives as readable message
        lines = ["**Alternative Suggestions:**\n"]
        for i, p in enumerate(alternatives.proposals, 1):
            lines.append(
                f"{i}. **{p.category}**: {p.description}\n"
                f"   Impact: {p.estimated_impact}\n"
                f"   Trade-off: {p.trade_off}"
            )
        return ChatResponse(
            type="conversation",
            message="\n".join(lines),
        )

    # ── Handle plan modification ─────────────────────────────────────────
    plan_row = await session.get(MachiningPlanModel, plan_id)
    if plan_row is None:
        from fastapi import HTTPException, status as http_status
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )

    plan_response = MachiningPlanResponse(**plan_row.plan_data)
    plan_response.plan_id = plan_row.id

    # Build minimal PlanningContext from plan data
    feature_stubs = []
    seen: set[str] = set()
    for op in plan_row.plan_data.get("operations", []):
        fid = op.get("feature_id")
        if fid and fid not in seen:
            seen.add(fid)
            feature_stubs.append(
                FeatureContext(id=fid, type="UNKNOWN", confidence=1.0)
            )
    context = PlanningContext(
        model_id=plan_row.model_id,
        material=plan_row.material,
        machine_type=plan_row.machine_type,
        features=feature_stubs,
    )

    result = await generate_refinement_diff(
        user_message=req.user_message,
        plan=plan_response,
        context=context,
    )

    if result["diff"].is_empty:
        return ChatResponse(
            type="conversation",
            message="I couldn't identify specific changes from your request. "
                    "Could you be more specific about what you'd like to modify?",
        )

    # Store as pending proposal — user must confirm
    ConsentManager.store_proposal(
        plan_id=plan_id,
        diff=result["diff"],
        preview_plan=result["preview_plan"],
        context=context,
        summary=result["summary"],
    )

    return ChatResponse(
        type="plan_proposal",
        explanation=result["summary"],
        proposed_plan=result["preview_plan"],
        version=plan_row.version,
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

    # Fetch intelligence → PlanningContext for richer narratives
    context = None
    try:
        from ai_service.ingestion import fetch_model_intelligence, adapt_intelligence
        intelligence = await fetch_model_intelligence(plan.model_id)
        context = adapt_intelligence(
            intelligence,
            material=plan.material,
            machine_type=plan.machine_type,
        )
    except Exception:
        logger.debug("Could not fetch intelligence — narrative will use plan data only")

    plan_response = MachiningPlanResponse(**plan.plan_data)
    plan_response.plan_id = plan.id

    if context is not None:
        text = await generate_narrative(plan_response, context)
    else:
        # Fallback: build minimal context from plan data
        from ai_service.schemas.planning_context import PlanningContext, FeatureContext
        feature_stubs = []
        seen: set[str] = set()
        for op in plan.plan_data.get("operations", []):
            fid = op.get("feature_id")
            if fid and fid not in seen:
                seen.add(fid)
                feature_stubs.append(
                    FeatureContext(id=fid, type="UNKNOWN", confidence=1.0)
                )
        fallback_ctx = PlanningContext(
            model_id=plan.model_id,
            material=plan.material,
            machine_type=plan.machine_type,
            features=feature_stubs,
        )
        text = await generate_narrative(plan_response, fallback_ctx)

    # Persist narrative to plan row
    plan.process_summary = text

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


# ── Version Rollback ──────────────────────────────────────────────────────────

@planning_router.post(
    "/{model_id}/rollback",
    response_model=MachiningPlanResponse,
    summary="Roll back to a previous plan version",
    description=(
        "Creates a new immutable version whose plan_data is cloned from "
        "the specified target version.  The new row has is_rollback=True "
        "and parent_version_id pointing at the source.  "
        "History is never deleted."
    ),
)
async def rollback(
    model_id: str,
    req: RollbackRequest,
    session: AsyncSession = Depends(get_session),
) -> MachiningPlanResponse:
    logger.info(
        "Rollback request: model=%s target_version=%d reason=%s",
        model_id, req.target_version, req.reason[:120],
    )
    restored = await rollback_plan(
        model_id=model_id,
        target_version=req.target_version,
        reason=req.reason,
        session=session,
    )
    return restored


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
            is_rollback=getattr(p, 'is_rollback', False),
            modification_reason=p.modification_reason,
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
