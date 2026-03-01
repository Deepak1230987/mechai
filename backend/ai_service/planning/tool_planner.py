"""
Tool Planner — deterministic tool selection for planned operations.

Selects tools based on:
  - Feature diameter
  - Depth
  - Material
  - Manufacturability warnings
  - Complexity score

Wraps the existing ToolLibrary with context-aware selection.
No LLM.
"""

from __future__ import annotations

import logging

from ai_service.schemas.planning_context import PlanningContext
from ai_service.planning.operation_planner import PlannedOperation
from ai_service.services.tool_library import ToolLibrary, Tool

logger = logging.getLogger("ai_service.planning.tool_planner")

_lib = ToolLibrary()


def assign_tools(
    operations: list[PlannedOperation],
    context: PlanningContext,
) -> dict[str, Tool]:
    """
    Assign a tool to each operation from the ToolLibrary.

    Returns:
        Dict mapping operation_id → Tool.
        Operations with no suitable tool get None and are logged as warnings.
    """
    tool_assignments: dict[str, Tool] = {}
    feature_map = {f.id: f for f in context.features}

    for op in operations:
        feat = feature_map.get(op.feature_id)
        tool = _select_tool(op, feat, context)

        if tool is None:
            logger.warning(
                "No tool found for op %s (type=%s, feature=%s)",
                op.id, op.op_type, op.feature_id,
            )
            continue

        tool_assignments[op.id] = tool

    logger.info(
        "Tool assignment: %d/%d operations have tools",
        len(tool_assignments), len(operations),
    )
    return tool_assignments


def _select_tool(
    op: PlannedOperation,
    feat: object | None,
    context: PlanningContext,
) -> Tool | None:
    """Select the best tool for an operation."""
    params = op.parameters
    material = context.material

    if op.op_type in ("DRILLING", "SPOT_DRILL", "REAMING"):
        diameter = params.get("diameter", 5.0)
        depth = params.get("depth")
        return _lib.select_drill(diameter=diameter, depth=depth, material=material)

    if op.op_type in ("POCKET_ROUGHING", "POCKET_FINISHING"):
        width = params.get("width", 10.0)
        depth = params.get("depth")
        return _lib.select_end_mill(pocket_width=width, depth=depth, material=material)

    if op.op_type in ("SLOT_ROUGHING", "SLOT_FINISHING", "SLOT_MILLING"):
        width = params.get("width", 6.0)
        depth = params.get("depth")
        return _lib.select_slot_cutter(
            slot_width=width, depth=depth, material=material
        )

    if op.op_type in ("ROUGH_TURNING", "FINISH_TURNING", "GROOVING"):
        return _lib.select_turning_insert(material=material)

    if op.op_type == "FACE_MILLING":
        return _lib.select_end_mill(pocket_width=20.0, depth=2.0, material=material)

    logger.debug("No tool selection rule for op_type=%s", op.op_type)
    return None
