"""
Planning Service — hybrid pipeline orchestrator.

Pipeline:
     1. Validate inputs  (machine_type, model exists, feature_ready)
     2. Fetch geometry metadata + detected features from DB
     3. Feature Validation Layer  →  FeatureValidator (DI boundary)
     4. Validation Logging        →  ValidationLogger (non-blocking)
     5. Rule Engine               →  operations + tools + setups + time
     6. Build baseline plan dict
     7. LangChain optimiser       →  optional LLM pass (graceful fallback)
     8. Plan Validator            →  structural + physical checks
     9. Compute version           →  next version for this model_id
    10. Persist plan              →  approved=False (human approval required)
    11. Return MachiningPlanResponse

Separation rules enforced:
    • No ML logic in this file.
    • No LLM logic in this file.
    • Feature validator = injected via abstract interface.
    • LangChain pipeline = separate module, called as black-box.
    • Plan validator     = separate module, called as black-box.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from cad_service.models import CADModel
from cad_worker.models import ModelFeature, ModelGeometry
from ai_service.models import MachiningPlan as MachiningPlanModel
from ai_service.schemas.machining_plan import (
    MachiningPlanResponse,
    ToolSpec,
    OperationSpec,
    SetupSpec,
    PlanningRequest,
)
from ai_service.services.rule_engine import plan_operations, group_into_setups
from ai_service.services.time_estimator import estimate_operation_time, estimate_total_time

# ── Hybrid layers ─────────────────────────────────────────────────────────────
from ai_service.services.feature_validator import FeatureValidator
from ai_service.services.feature_validator.deterministic_validator import (
    DeterministicFeatureValidator,
)
from ai_service.services.feature_validator.validation_logger import ValidationLogger
from ai_service.services.langchain_pipeline import optimize_plan
from ai_service.services.plan_validator import PlanValidator, PlanValidationError

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
    Generate a versioned machining plan (approved=False).

    Args:
        req:        PlanningRequest with model_id, material, machine_type.
        session:    Async DB session (commit handled by caller / DI).
        validator:  Optional FeatureValidator override (DI).  Defaults to
                    DeterministicFeatureValidator.

    Raises:
        HTTPException on invalid input, missing data, or plan validation failure.
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

    # ── 3. Fetch geometry metadata ───────────────────────────────────────────
    geom_result = await session.execute(
        select(ModelGeometry).where(ModelGeometry.model_id == req.model_id)
    )
    geom = geom_result.scalars().first()
    if geom is None or not geom.feature_ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Feature extraction not ready (BRep required for planning)",
        )

    geometry_metadata: dict = {
        "volume": geom.volume,
        "surface_area": geom.surface_area,
        "bounding_box": geom.bounding_box or {},
        "face_count": geom.face_count,
        "edge_count": geom.edge_count,
    }

    # ── 4. Fetch raw features ────────────────────────────────────────────────
    feat_result = await session.execute(
        select(ModelFeature).where(ModelFeature.model_id == req.model_id)
    )
    features_db = feat_result.scalars().all()
    if not features_db:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No features detected on this model — cannot generate plan",
        )

    raw_features: list[dict] = [
        {
            "id": f.id,
            "type": f.type,
            "confidence": getattr(f, "confidence", 1.0),
            "dimensions": f.dimensions or {},
            "depth": f.depth,
            "diameter": f.diameter,
            "axis": f.axis,
        }
        for f in features_db
    ]

    # ── 5. Feature Validation Layer (ML boundary) ────────────────────────────
    validated_features = validator.validate(raw_features, geometry_metadata)
    if not validated_features:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="All features were rejected by validation — cannot generate plan",
        )

    logger.info(
        "Feature validation: %d raw → %d validated",
        len(raw_features),
        len(validated_features),
    )

    # ── 6. Validation Logging (non-blocking) ─────────────────────────────────
    vl = ValidationLogger(session)
    await vl.log(
        model_id=req.model_id,
        raw_features=raw_features,
        validated_features=validated_features,
        geometry_snapshot=geometry_metadata,
    )

    # ── 7. Rule Engine ───────────────────────────────────────────────────────
    planned_ops = plan_operations(validated_features, req.material, req.machine_type)
    if not planned_ops:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rule engine produced no operations — check features and machine type",
        )

    # ── 8. Build tool de-duplication map + operation specs ───────────────────
    tool_map: dict[str, ToolSpec] = {}
    for op in planned_ops:
        if op.tool and op.tool.id not in tool_map:
            tool_map[op.tool.id] = ToolSpec(
                id=op.tool.id,
                type=op.tool.type,
                diameter=op.tool.diameter,
                max_depth=op.tool.max_depth,
                recommended_rpm_min=op.tool.rpm_min,
                recommended_rpm_max=op.tool.rpm_max,
            )

    operation_specs: list[OperationSpec] = []
    operation_times: list[float] = []

    for op in planned_ops:
        tool_type = op.tool.type if op.tool else "FLAT_END_MILL"
        tool_dia = op.tool.diameter if op.tool else 10.0
        tool_id = op.tool.id if op.tool else "unknown"

        t = estimate_operation_time(
            op_type=op.op_type,
            tool_type=tool_type,
            tool_diameter=tool_dia,
            material=req.material,
            parameters=op.parameters,
        )
        operation_times.append(t)

        operation_specs.append(OperationSpec(
            id=op.id,
            feature_id=op.feature_id,
            type=op.op_type,
            tool_id=tool_id,
            parameters=op.parameters,
            estimated_time=round(t, 2),
        ))

    total_time = round(estimate_total_time(operation_times), 2)

    # ── 9. Group into setups ─────────────────────────────────────────────────
    setup_dicts = group_into_setups(planned_ops, req.machine_type)
    setup_specs = [
        SetupSpec(
            setup_id=s["setup_id"],
            orientation=s["orientation"],
            operations=s["operations"],
        )
        for s in setup_dicts
    ]

    # ── 10. Build baseline plan dict ─────────────────────────────────────────
    base_plan = MachiningPlanResponse(
        model_id=req.model_id,
        material=req.material,
        machine_type=req.machine_type,
        setups=setup_specs,
        operations=operation_specs,
        tools=list(tool_map.values()),
        estimated_time=total_time,
        version=1,       # placeholder — final version computed below
        approved=False,
    )
    base_plan_dict = base_plan.model_dump()

    # ── 11. LangChain optimiser (optional, graceful fallback) ────────────────
    optimised_dict = await optimize_plan(
        base_plan=base_plan_dict,
        validated_features=validated_features,
        material=req.material,
        machine_type=req.machine_type,
    )

    # ── 12. Plan Validator ───────────────────────────────────────────────────
    pv = PlanValidator(validated_features, req.material, req.machine_type)
    try:
        validated_plan_dict = pv.validate(optimised_dict)
    except PlanValidationError as exc:
        logger.warning(
            "LLM-optimised plan failed validation (%s) — falling back to baseline",
            exc.errors,
        )
        # Validate baseline as safety net (should always pass)
        try:
            validated_plan_dict = pv.validate(base_plan_dict)
        except PlanValidationError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Both optimised and baseline plans failed validation",
            )

    # ── 13. Compute next version ─────────────────────────────────────────────
    max_version_result = await session.execute(
        select(func.coalesce(func.max(MachiningPlanModel.version), 0)).where(
            MachiningPlanModel.model_id == req.model_id
        )
    )
    next_version: int = max_version_result.scalar_one() + 1

    # ── 14. Assemble final response ──────────────────────────────────────────
    # Overlay version + approved onto validated plan
    validated_plan_dict["version"] = next_version
    validated_plan_dict["approved"] = False

    final_plan = MachiningPlanResponse(**validated_plan_dict)

    # ── 15. Persist to DB (approved=False) ───────────────────────────────────
    plan_row = MachiningPlanModel(
        id=str(uuid.uuid4()),
        model_id=req.model_id,
        material=req.material,
        machine_type=req.machine_type,
        plan_data=final_plan.model_dump(),
        estimated_time=final_plan.estimated_time,
        version=next_version,
        approved=False,
    )
    session.add(plan_row)

    logger.info(
        "Generated plan v%d for model=%s: %d ops, %d tools, %.1f s total "
        "(approved=False)",
        next_version,
        req.model_id,
        len(final_plan.operations),
        len(final_plan.tools),
        final_plan.estimated_time,
    )
    return final_plan
