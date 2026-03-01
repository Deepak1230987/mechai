"""
Planning Service — Hybrid Deterministic + LLM Co-Planner Orchestrator.

New pipeline (Phase B):
     1. Validate inputs  (machine_type, model exists, READY status)
     2. Fetch ManufacturingGeometryReport via CAD Service HTTP API
     3. Adapt intelligence report → PlanningContext (typed Pydantic)
     4. Feature Validation Layer   →  FeatureValidator (DI boundary)
     5. Validation Logging         →  ValidationLogger (non-blocking)
     6. Deterministic Base Plan    →  base_plan_generator pipeline
     7. LLM Co-Planner            →  structured LLMDiff (not a full plan)
     8. Diff Validator             →  referential integrity + safety
     9. Plan Merger                →  apply validated diff to base plan
    10. Final Plan Validator       →  structural + physical checks
    11. Risk Integration           →  map flags to operations
    12. Strategy Generation        →  CONSERVATIVE / OPTIMIZED / AGGRESSIVE
    13. Narrative Generation       →  LLM process narrative (async)
    14. Persist versioned plan     →  PlanVersionService
    15. Return MachiningPlanResponse

Data source:
    ManufacturingGeometryReport (single source of truth) fetched from
    CAD Service GET /models/{model_id}/intelligence.

Architecture:
    LLM actively improves planning — but NEVER bypasses deterministic safety.
    LLM output is always a structured diff, not a full plan replacement.
    Deterministic validator gates every diff before merger applies it.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from cad_service.models import CADModel

# ── New pipeline modules ──────────────────────────────────────────────────────
from ai_service.ingestion import fetch_model_intelligence, adapt_intelligence
from ai_service.planning.base_plan_generator import generate_base_plan
from ai_service.planning.llm_coplanner import refine_plan_with_llm
from ai_service.planning.plan_validator import validate_llm_diff, validate_final_plan
from ai_service.planning.plan_merger import merge_base_and_llm
from ai_service.planning.strategy_generator import generate_strategies
from ai_service.reasoning.narrative_generator import generate_narrative
from ai_service.versioning.plan_version_service import PlanVersionService
from ai_service.versioning.rollback_service import RollbackService

from ai_service.schemas.machining_plan import (
    MachiningPlanResponse,
    PlanningRequest,
)

# ── Feature validation (kept from Phase A) ────────────────────────────────────
from ai_service.services.feature_validator import FeatureValidator
from ai_service.services.feature_validator.deterministic_validator import (
    DeterministicFeatureValidator,
)
from ai_service.services.feature_validator.validation_logger import ValidationLogger

logger = logging.getLogger(__name__)

# ── Valid inputs ──────────────────────────────────────────────────────────────

_VALID_MACHINE_TYPES = {"MILLING_3AXIS", "LATHE"}


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_plan(
    req: PlanningRequest,
    session: AsyncSession,
    *,
    validator: FeatureValidator | None = None,
) -> MachiningPlanResponse:
    """
    Generate a versioned machining plan via the hybrid pipeline.

    Steps:
        1.  Validate inputs
        2.  Fetch & adapt intelligence → PlanningContext
        3.  Feature validation (DI)
        4.  Deterministic base plan
        5.  LLM co-planner → structured diff
        6.  Validate diff → merge if safe
        7.  Final plan validation
        8.  Strategies + narrative
        9.  Persist (version 1, approval_status=DRAFT)

    Args:
        req:        PlanningRequest with model_id, material, machine_type.
        session:    Async DB session.
        validator:  Optional FeatureValidator override (DI).

    Raises:
        HTTPException on invalid input, missing data, or validation failure.
    """

    if validator is None:
        validator = DeterministicFeatureValidator()

    # ── 1. Validate machine type ─────────────────────────────────────────────
    if req.machine_type not in _VALID_MACHINE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"machine_type must be one of {_VALID_MACHINE_TYPES}",
        )

    # ── 2. Verify model exists and is READY ──────────────────────────────────
    model = await session.get(CADModel, req.model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model {req.model_id} not found",
        )
    if model.status != "READY":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Model status is '{model.status}', must be READY for planning",
        )

    # ── 3. Fetch ManufacturingGeometryReport ─────────────────────────────────
    try:
        intelligence = await fetch_model_intelligence(req.model_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Manufacturing intelligence not available: {exc}",
        )

    # ── 4. Adapt to PlanningContext ──────────────────────────────────────────
    context = adapt_intelligence(
        intelligence,
        material=req.material,
        machine_type=req.machine_type,
    )

    if not context.features:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No features in intelligence report — cannot generate plan",
        )

    # ── 5. Feature Validation Layer (ML boundary) ────────────────────────────
    raw_feature_dicts = [f.model_dump() for f in context.features]
    geometry_dict = context.geometry.model_dump() if context.geometry else {}
    validated_feature_dicts = validator.validate(raw_feature_dicts, geometry_dict)

    if not validated_feature_dicts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All features were rejected by validation — cannot generate plan",
        )

    logger.info(
        "Feature validation: %d raw → %d validated",
        len(raw_feature_dicts),
        len(validated_feature_dicts),
    )

    # ── 6. Validation Logging (non-blocking) ─────────────────────────────────
    vl = ValidationLogger(session)
    await vl.log(
        model_id=req.model_id,
        raw_features=raw_feature_dicts,
        validated_features=validated_feature_dicts,
        geometry_snapshot=geometry_dict,
    )

    # ── 7. Deterministic Base Plan ───────────────────────────────────────────
    base_plan = generate_base_plan(context)

    if not base_plan.operations:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Deterministic planner produced no operations — check features",
        )

    logger.info(
        "Base plan: %d ops, %d tools, %d setups, %.1fs",
        len(base_plan.operations),
        len(base_plan.tools),
        len(base_plan.setups),
        base_plan.estimated_time,
    )

    # ── 8. LLM Co-Planner → structured diff ─────────────────────────────────
    llm_diff = await refine_plan_with_llm(base_plan, context)

    final_plan = base_plan  # default: use base plan as-is

    if not llm_diff.is_empty:
        # ── 9. Validate the diff ─────────────────────────────────────────────
        diff_result = validate_llm_diff(base_plan, llm_diff, context)

        if diff_result.valid:
            # ── 10. Merge validated diff into base plan ──────────────────────
            merged = merge_base_and_llm(base_plan, llm_diff)

            # ── 11. Validate the merged plan ─────────────────────────────────
            plan_result = validate_final_plan(merged, context)
            if plan_result.valid:
                final_plan = merged
                final_plan.llm_justification = llm_diff.justification
                logger.info(
                    "LLM diff applied: %d changes, justification=%s",
                    llm_diff.change_count,
                    (llm_diff.justification or "")[:80],
                )
            else:
                logger.warning(
                    "Merged plan failed final validation (%s) — using base plan",
                    plan_result.errors[:3],
                )
        else:
            logger.warning(
                "LLM diff rejected by validator (%s) — using base plan",
                diff_result.errors[:3],
            )
    else:
        logger.info("LLM co-planner returned empty diff — base plan is optimal")
        final_plan.generation_explanation = (
            "Deterministic plan — LLM found no improvements."
        )

    # ── 12. Strategy Generation ──────────────────────────────────────────────
    strategies = generate_strategies(base_plan, final_plan, context)
    final_plan.strategies = strategies
    if strategies:
        final_plan.selected_strategy = strategies[0].name  # default: first

    # ── 13. Narrative Generation (async, graceful fallback) ──────────────────
    try:
        narrative = await generate_narrative(final_plan, context)
    except Exception:
        logger.debug("Narrative generation failed — continuing without it")
        narrative = None

    # ── 14. Persist versioned plan ───────────────────────────────────────────
    version_svc = PlanVersionService(session)
    plan_row = await version_svc.save_initial_plan(
        plan=final_plan,
        process_summary=narrative,
    )

    logger.info(
        "Generated plan v%d for model=%s: %d ops, %d tools, %.1f s total "
        "(approval_status=DRAFT)",
        final_plan.version,
        req.model_id,
        len(final_plan.operations),
        len(final_plan.tools),
        final_plan.estimated_time,
    )
    return final_plan


# ── Rollback (separate from base planning — does NOT re-trigger LLM) ─────────

async def rollback_plan(
    model_id: str,
    target_version: int,
    reason: str,
    session: AsyncSession,
) -> MachiningPlanResponse:
    """
    Roll back to a previous plan version.

    Creates a new immutable version with is_rollback=True.
    Does NOT re-trigger LLM or base planning logic.

    Args:
        model_id:       The model to roll back.
        target_version: Version number to restore.
        reason:         Human-readable rollback reason.
        session:        Async DB session.

    Returns:
        MachiningPlanResponse for the newly created rollback version.

    Raises:
        HTTPException on invalid target version.
    """
    rollback_svc = RollbackService(session)

    try:
        row = await rollback_svc.rollback_to_version(
            model_id=model_id,
            target_version_number=target_version,
            reason=reason,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    response = MachiningPlanResponse(**row.plan_data)
    response.plan_id = row.id
    response.version = row.version
    response.is_rollback = True
    response.parent_version_id = row.parent_version_id

    logger.info(
        "Rollback complete: model=%s target_v=%d → new_v=%d (reason=%s)",
        model_id,
        target_version,
        row.version,
        reason[:80],
    )
    return response
