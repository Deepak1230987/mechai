"""
Planning Service — orchestrator for deterministic machining plan generation.

Pipeline:
    1. Fetch features from model_features table (via model_id)
    2. Validate feature_ready flag
    3. Run rule engine  →  operations + tool selection
    4. Run time estimator  →  per-operation + total time
    5. Group into setups
    6. Build MachiningPlanResponse
    7. Persist plan to machining_plans table
    8. Return plan

No AI calls.  No geometry processing.  Only uses stored Feature records.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
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

logger = logging.getLogger(__name__)

# ── Valid inputs ──────────────────────────────────────────────────────────────

_VALID_MACHINE_TYPES = {"MILLING_3AXIS", "LATHE"}


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_plan(
    req: PlanningRequest,
    session: AsyncSession,
) -> MachiningPlanResponse:
    """
    Generate a complete deterministic machining plan.

    Raises HTTPException on invalid input or missing data.
    """

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

    # ── 3. Verify feature_ready ──────────────────────────────────────────────
    geom_result = await session.execute(
        select(ModelGeometry).where(ModelGeometry.model_id == req.model_id)
    )
    geom = geom_result.scalars().first()
    if geom is None or not geom.feature_ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Feature extraction not ready (BRep required for planning)",
        )

    # ── 4. Fetch features ────────────────────────────────────────────────────
    feat_result = await session.execute(
        select(ModelFeature).where(ModelFeature.model_id == req.model_id)
    )
    features_db = feat_result.scalars().all()
    if not features_db:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No features detected on this model — cannot generate plan",
        )

    # Convert ORM rows → plain dicts for the rule engine
    features: list[dict] = []
    for f in features_db:
        features.append({
            "id": f.id,
            "type": f.type,
            "dimensions": f.dimensions or {},
            "depth": f.depth,
            "diameter": f.diameter,
            "axis": f.axis,
        })

    # ── 5. Run rule engine ───────────────────────────────────────────────────
    planned_ops = plan_operations(features, req.material, req.machine_type)
    if not planned_ops:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rule engine produced no operations — check features and machine type",
        )

    # ── 6. Build tool de-duplication map ─────────────────────────────────────
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

    # ── 7. Estimate time per operation ───────────────────────────────────────
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

    # ── 8. Group into setups ─────────────────────────────────────────────────
    setup_dicts = group_into_setups(planned_ops, req.machine_type)
    setup_specs = [
        SetupSpec(
            setup_id=s["setup_id"],
            orientation=s["orientation"],
            operations=s["operations"],
        )
        for s in setup_dicts
    ]

    # ── 9. Assemble response ─────────────────────────────────────────────────
    plan = MachiningPlanResponse(
        model_id=req.model_id,
        material=req.material,
        machine_type=req.machine_type,
        setups=setup_specs,
        operations=operation_specs,
        tools=list(tool_map.values()),
        estimated_time=total_time,
    )

    # ── 10. Persist to DB ────────────────────────────────────────────────────
    plan_row = MachiningPlanModel(
        id=str(uuid.uuid4()),
        model_id=req.model_id,
        material=req.material,
        machine_type=req.machine_type,
        plan_data=plan.model_dump(),
        estimated_time=total_time,
    )
    session.add(plan_row)
    # Commit happens via get_session context manager

    logger.info(
        "Generated plan for model=%s: %d ops, %d tools, %.1f s total",
        req.model_id,
        len(operation_specs),
        len(tool_map),
        total_time,
    )
    return plan
