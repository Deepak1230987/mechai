"""
Plan Merger — applies validated LLM diffs to the deterministic base plan.

Safety rules:
  • Deterministic risk constraints CANNOT be overridden
  • Safety operations (spot drill for centering, finishing passes for
    tight tolerances) CANNOT be removed
  • Datum references CANNOT be changed
  • Every conflict is logged

Returns ImprovedMachiningPlan (same schema, different data).
"""

from __future__ import annotations

import copy
import logging
import uuid

from ai_service.schemas.llm_diff_schema import LLMDiff
from ai_service.schemas.machining_plan import (
    MachiningPlanResponse,
    OperationSpec,
    ToolSpec,
)

logger = logging.getLogger("ai_service.planning.plan_merger")

# Operations that must never be removed by LLM
_SAFETY_OP_TYPES = {"SPOT_DRILL", "REAMING"}


def merge_base_and_llm(
    base_plan: MachiningPlanResponse,
    diff: LLMDiff,
) -> MachiningPlanResponse:
    """
    Apply a validated LLM diff to the base plan.

    Returns:
        New MachiningPlanResponse with diff applied.
        base_plan is NOT mutated.
    """
    if diff.is_empty:
        logger.info("Empty diff — returning base plan unchanged")
        plan = base_plan.model_copy(deep=True)
        plan.llm_justification = diff.justification
        return plan

    # Deep copy to avoid mutations
    plan = base_plan.model_copy(deep=True)
    conflicts: list[str] = []

    # ── 1. Apply operation reorders ──────────────────────────────────────
    if diff.operation_reorders:
        plan.operations = _apply_reorders(plan.operations, diff.operation_reorders, conflicts)

    # ── 2. Apply tool changes ────────────────────────────────────────────
    if diff.tool_changes:
        _apply_tool_changes(plan, diff.tool_changes, conflicts)

    # ── 3. Apply parameter changes ───────────────────────────────────────
    if diff.parameter_changes:
        _apply_parameter_changes(plan.operations, diff.parameter_changes, conflicts)

    # ── 4. Apply setup modifications ─────────────────────────────────────
    if diff.setup_modifications:
        _apply_setup_modifications(plan, diff.setup_modifications, conflicts)

    # ── 5. Apply operation additions ─────────────────────────────────────
    if diff.operation_additions:
        _apply_operation_additions(plan, diff.operation_additions, conflicts)

    # ── 6. Update metadata ───────────────────────────────────────────────
    plan.llm_justification = diff.justification
    if diff.estimated_time_change != 0:
        plan.estimated_time = max(1.0, plan.estimated_time + diff.estimated_time_change)

    if conflicts:
        logger.warning(
            "Merge completed with %d conflicts suppressed: %s",
            len(conflicts), conflicts,
        )
    else:
        logger.info("Merge completed cleanly: %d changes applied", diff.change_count)

    return plan


# ── Internal helpers ──────────────────────────────────────────────────────────

def _apply_reorders(
    operations: list[OperationSpec],
    reorders: list,
    conflicts: list[str],
) -> list[OperationSpec]:
    """Reorder operations by new_position."""
    op_map = {op.id: op for op in operations}
    result = list(operations)

    for reorder in reorders:
        op = op_map.get(reorder.operation_id)
        if op is None:
            conflicts.append(f"Reorder: operation {reorder.operation_id} not found")
            continue

        # Safety: don't move safety ops before their parent drilling op
        if op.type in _SAFETY_OP_TYPES:
            conflicts.append(
                f"Reorder suppressed: cannot move safety operation {op.id} ({op.type})"
            )
            continue

        try:
            result.remove(op)
            pos = min(reorder.new_position, len(result))
            result.insert(pos, op)
        except ValueError:
            conflicts.append(f"Reorder: could not move {reorder.operation_id}")

    return result


def _apply_tool_changes(
    plan: MachiningPlanResponse,
    tool_changes: list,
    conflicts: list[str],
) -> None:
    """Swap tool assignments for operations."""
    op_map = {op.id: op for op in plan.operations}
    tool_map = {t.id: t for t in plan.tools}

    for tc in tool_changes:
        op = op_map.get(tc.operation_id)
        if op is None:
            conflicts.append(f"Tool change: operation {tc.operation_id} not found")
            continue

        # Safety: don't change tools on safety operations
        if op.type in _SAFETY_OP_TYPES:
            conflicts.append(
                f"Tool change suppressed: cannot change tool on safety op {op.id}"
            )
            continue

        # Add new tool to plan if not already present
        new_tool_id = tc.proposed_tool_id
        if new_tool_id and new_tool_id not in tool_map:
            new_tool = ToolSpec(
                id=new_tool_id,
                type=tc.proposed_tool_type or "FLAT_END_MILL",
                diameter=tc.proposed_tool_diameter or 10.0,
                max_depth=0,
            )
            plan.tools.append(new_tool)
            tool_map[new_tool_id] = new_tool

        op.tool_id = new_tool_id


def _apply_parameter_changes(
    operations: list[OperationSpec],
    param_changes: list,
    conflicts: list[str],
) -> None:
    """Modify cutting parameters on operations."""
    op_map = {op.id: op for op in operations}

    for pc in param_changes:
        op = op_map.get(pc.operation_id)
        if op is None:
            conflicts.append(f"Param change: operation {pc.operation_id} not found")
            continue

        if pc.parameter_name in ("feature_id", "id", "type", "tool_id"):
            conflicts.append(
                f"Param change suppressed: cannot modify immutable field {pc.parameter_name}"
            )
            continue

        op.parameters[pc.parameter_name] = pc.new_value


def _apply_setup_modifications(
    plan: MachiningPlanResponse,
    setup_mods: list,
    conflicts: list[str],
) -> None:
    """Apply setup merge/split/reorder operations."""
    setup_map = {s.setup_id: s for s in plan.setups}

    for mod in setup_mods:
        if mod.action == "MERGE" and len(mod.setup_ids) >= 2:
            # Merge: combine all operations into first setup
            target_id = mod.setup_ids[0]
            target = setup_map.get(target_id)
            if target is None:
                conflicts.append(f"Setup merge: target {target_id} not found")
                continue

            for sid in mod.setup_ids[1:]:
                source = setup_map.get(sid)
                if source is None:
                    conflicts.append(f"Setup merge: source {sid} not found")
                    continue
                target.operations.extend(source.operations)
                plan.setups.remove(source)
                del setup_map[sid]

            if mod.proposed_orientation:
                target.orientation = mod.proposed_orientation

        elif mod.action == "REORDER":
            # Move specific operations between setups
            for op_id in mod.operations_to_move:
                # Find source setup
                moved = False
                for setup in plan.setups:
                    if op_id in setup.operations:
                        setup.operations.remove(op_id)
                        moved = True
                        break
                if not moved:
                    conflicts.append(f"Setup reorder: op {op_id} not found in any setup")
                    continue
                # Add to first target setup
                if mod.setup_ids:
                    target = setup_map.get(mod.setup_ids[0])
                    if target:
                        target.operations.append(op_id)
        else:
            conflicts.append(f"Unsupported setup action: {mod.action}")


def _apply_operation_additions(
    plan: MachiningPlanResponse,
    additions: list,
    conflicts: list[str],
) -> None:
    """Add new operations proposed by LLM."""
    op_map = {op.id: i for i, op in enumerate(plan.operations)}

    for add in additions:
        new_op = OperationSpec(
            id=str(uuid.uuid4()),
            feature_id=add.feature_id,
            type=add.op_type,
            tool_id=add.tool_type or "unknown",
            parameters=add.parameters,
            estimated_time=0,
        )

        if add.insert_after and add.insert_after in op_map:
            idx = op_map[add.insert_after] + 1
            plan.operations.insert(idx, new_op)
        else:
            plan.operations.append(new_op)

        # Add to first setup that has operations for this feature
        placed = False
        for setup in plan.setups:
            if any(
                op.feature_id == add.feature_id
                for op in plan.operations
                if op.id in setup.operations
            ):
                setup.operations.append(new_op.id)
                placed = True
                break
        if not placed and plan.setups:
            plan.setups[0].operations.append(new_op.id)

        # Rebuild op_map
        op_map = {op.id: i for i, op in enumerate(plan.operations)}
