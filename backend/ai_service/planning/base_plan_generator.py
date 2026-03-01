"""
Base Plan Generator — orchestrates deterministic plan creation.

Pipeline:
  1. setup_planner   → group features into setups
  2. operation_planner → map features to operations
  3. tool_planner    → assign tools to operations
  4. risk_integrator → attach warnings to operations
  5. time_estimator  → compute per-op and total time
  6. Assemble MachiningPlanResponse (BaseMachiningPlan)

This is the deterministic foundation. The LLM co-planner operates
on top of the output of this function.
"""

from __future__ import annotations

import logging

from ai_service.schemas.planning_context import PlanningContext
from ai_service.schemas.machining_plan import (
    MachiningPlanResponse,
    SetupSpec,
    OperationSpec,
    ToolSpec,
    RiskItem,
)
from ai_service.planning.setup_planner import plan_setups
from ai_service.planning.operation_planner import plan_operations, PlannedOperation
from ai_service.planning.tool_planner import assign_tools
from ai_service.planning.risk_integrator import integrate_risks
from ai_service.services.time_estimator import estimate_operation_time, estimate_total_time
from ai_service.services.tool_library import Tool

logger = logging.getLogger("ai_service.planning.base_plan_generator")


def generate_base_plan(context: PlanningContext) -> MachiningPlanResponse:
    """
    Generate a complete deterministic base machining plan.

    Args:
        context: PlanningContext from the intelligence adapter.

    Returns:
        MachiningPlanResponse with all fields populated.
        version=1, approved=False, selected_strategy="CONSERVATIVE".
    """
    # ── 1. Plan setups ───────────────────────────────────────────────────
    setup_dicts = plan_setups(context)

    # Build feature→setup lookup
    feature_to_setup: dict[str, str] = {}
    for s in setup_dicts:
        for fid in s["feature_ids"]:
            feature_to_setup[fid] = s["setup_id"]

    # ── 2. Plan operations ───────────────────────────────────────────────
    planned_ops = plan_operations(context)

    if not planned_ops:
        logger.warning("No operations generated for model=%s", context.model_id)

    # ── 3. Assign tools ─────────────────────────────────────────────────
    tool_assignments = assign_tools(planned_ops, context)

    # ── 4. Integrate risks ──────────────────────────────────────────────
    risks = integrate_risks(planned_ops, context)

    # ── 5. Build specs + compute times ──────────────────────────────────
    tool_map: dict[str, ToolSpec] = {}
    operation_specs: list[OperationSpec] = []
    operation_times: list[float] = []

    for op in planned_ops:
        tool: Tool | None = tool_assignments.get(op.id)

        tool_id = "unknown"
        tool_type = "FLAT_END_MILL"
        tool_dia = 10.0

        if tool is not None:
            tool_id = tool.id
            tool_type = tool.type
            tool_dia = tool.diameter

            if tool.id not in tool_map:
                tool_map[tool.id] = ToolSpec(
                    id=tool.id,
                    type=tool.type,
                    diameter=tool.diameter,
                    max_depth=tool.max_depth,
                    recommended_rpm_min=tool.rpm_min,
                    recommended_rpm_max=tool.rpm_max,
                )

        t = estimate_operation_time(
            op_type=op.op_type,
            tool_type=tool_type,
            tool_diameter=tool_dia,
            material=context.material,
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

    # ── 6. Assign operations to setups ──────────────────────────────────
    # Map operations to the setup that owns their feature
    setup_ops: dict[str, list[str]] = {s["setup_id"]: [] for s in setup_dicts}
    for op in planned_ops:
        sid = feature_to_setup.get(op.feature_id)
        if sid and sid in setup_ops:
            setup_ops[sid].append(op.id)
        elif setup_dicts:
            # Fallback: put in first setup
            setup_ops[setup_dicts[0]["setup_id"]].append(op.id)

    setup_specs = [
        SetupSpec(
            setup_id=s["setup_id"],
            orientation=s["orientation"],
            datum_face_id=s.get("datum_face_id"),
            operations=setup_ops.get(s["setup_id"], []),
        )
        for s in setup_dicts
    ]

    # ── 7. Assemble base plan ───────────────────────────────────────────
    base_plan = MachiningPlanResponse(
        model_id=context.model_id,
        material=context.material,
        machine_type=context.machine_type,
        setups=setup_specs,
        operations=operation_specs,
        tools=list(tool_map.values()),
        risks=risks,
        strategies=[],  # Populated by strategy_generator
        selected_strategy="CONSERVATIVE",
        estimated_time=total_time,
        version=1,
        approved=False,
        approval_status="DRAFT",
    )

    logger.info(
        "Base plan generated: model=%s ops=%d tools=%d setups=%d risks=%d time=%.1fs",
        context.model_id,
        len(operation_specs),
        len(tool_map),
        len(setup_specs),
        len(risks),
        total_time,
    )
    return base_plan
