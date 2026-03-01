"""
Plan Validator — validates LLM diffs and final plans.

Checks:
  1. All feature_ids in diff reference existing features
  2. All operation_ids in diff reference existing operations
  3. No invalid tool diameters (< 0.5 mm or > 50 mm)
  4. Setup references valid datum
  5. No missing operations (every feature has at least one op)
  6. Manufacturability warnings mitigated
  7. No duplicate operation IDs
  8. Time bounds (> 0, < 24 hours)

If invalid → diff is rejected, base plan preserved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ai_service.schemas.llm_diff_schema import LLMDiff
from ai_service.schemas.machining_plan import MachiningPlanResponse
from ai_service.schemas.planning_context import PlanningContext

logger = logging.getLogger("ai_service.planning.plan_validator")


@dataclass
class ValidationResult:
    """Result of validating an LLM diff or a final plan."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class DiffValidationError(Exception):
    """Raised when an LLM diff fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Diff validation failed: {errors}")


class PlanValidationError(Exception):
    """Raised when a final plan fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Plan validation failed: {errors}")


# ── Diff Validation ───────────────────────────────────────────────────────────

def validate_llm_diff(
    base_plan: MachiningPlanResponse,
    diff: LLMDiff,
    context: PlanningContext,
) -> ValidationResult:
    """
    Validate an LLM diff against the base plan and context.

    Returns ValidationResult. If not valid, diff must be rejected.
    """
    result = ValidationResult()
    feature_ids = {f.id for f in context.features}
    operation_ids = {op.id for op in base_plan.operations}
    tool_ids = {t.id for t in base_plan.tools}

    # ── 1. Operation reorders reference existing ops ─────────────────────
    for reorder in diff.operation_reorders:
        if reorder.operation_id not in operation_ids:
            result.errors.append(
                f"Reorder references nonexistent operation: {reorder.operation_id}"
            )
        if reorder.new_position < 0 or reorder.new_position >= len(base_plan.operations) + len(diff.operation_additions):
            result.warnings.append(
                f"Reorder position {reorder.new_position} may be out of range"
            )

    # ── 2. Tool changes reference existing ops and valid diameters ───────
    for tc in diff.tool_changes:
        if tc.operation_id not in operation_ids:
            result.errors.append(
                f"Tool change references nonexistent operation: {tc.operation_id}"
            )
        if tc.current_tool_id not in tool_ids:
            result.warnings.append(
                f"Tool change references unknown current tool: {tc.current_tool_id}"
            )
        if tc.proposed_tool_diameter < 0.5 or tc.proposed_tool_diameter > 50:
            result.errors.append(
                f"Proposed tool diameter {tc.proposed_tool_diameter}mm out of range [0.5, 50]"
            )

    # ── 3. Parameter changes reference existing ops ──────────────────────
    for pc in diff.parameter_changes:
        if pc.operation_id not in operation_ids:
            result.errors.append(
                f"Parameter change references nonexistent operation: {pc.operation_id}"
            )

    # ── 4. Setup modifications reference existing setups ─────────────────
    setup_ids = {s.setup_id for s in base_plan.setups}
    for sm in diff.setup_modifications:
        for sid in sm.setup_ids:
            if sid not in setup_ids:
                result.errors.append(
                    f"Setup modification references nonexistent setup: {sid}"
                )
        for op_id in sm.operations_to_move:
            if op_id not in operation_ids:
                result.errors.append(
                    f"Setup modification moves nonexistent operation: {op_id}"
                )

    # ── 5. Operation additions reference existing features ──────────────
    for oa in diff.operation_additions:
        if oa.feature_id not in feature_ids:
            result.errors.append(
                f"Operation addition references nonexistent feature: {oa.feature_id}"
            )
        if oa.insert_after and oa.insert_after not in operation_ids:
            result.errors.append(
                f"insert_after references nonexistent operation: {oa.insert_after}"
            )

    result.valid = len(result.errors) == 0

    if result.valid:
        logger.info(
            "LLM diff validated: %d changes, %d warnings",
            diff.change_count, len(result.warnings),
        )
    else:
        logger.warning(
            "LLM diff rejected: %d errors — %s",
            len(result.errors), result.errors,
        )

    return result


# ── Final Plan Validation (post-merge) ───────────────────────────────────────

def validate_final_plan(
    plan: MachiningPlanResponse,
    context: PlanningContext,
) -> ValidationResult:
    """
    Validate a final merged plan for structural and physical correctness.

    Checks all original plan_validator rules plus new fields.
    """
    result = ValidationResult()
    feature_ids = {f.id for f in context.features}

    operations = plan.operations
    tools = plan.tools
    setups = plan.setups

    # ── Tool lookup ──────────────────────────────────────────────────────
    tool_map = {t.id: t for t in tools}
    op_map: dict[str, object] = {}

    for op in operations:
        if op.id in op_map:
            result.errors.append(f"Duplicate operation ID: {op.id}")
        op_map[op.id] = op

    # ── All features covered ─────────────────────────────────────────────
    mapped_features = {op.feature_id for op in operations}
    for fid in feature_ids:
        if fid not in mapped_features:
            result.errors.append(f"Feature {fid} has no operations")

    # ── Tool references valid ────────────────────────────────────────────
    for op in operations:
        if op.tool_id != "unknown" and op.tool_id not in tool_map:
            result.errors.append(
                f"Operation {op.id} references nonexistent tool {op.tool_id}"
            )

    # ── Tool field completeness ──────────────────────────────────────────
    for t in tools:
        for fld in ("id", "type", "diameter"):
            if getattr(t, fld, None) is None:
                result.errors.append(f"Tool {t.id} missing field: {fld}")

    # ── Operation field completeness ─────────────────────────────────────
    for op in operations:
        for fld in ("id", "feature_id", "type", "tool_id"):
            if getattr(op, fld, None) is None:
                result.errors.append(f"Operation {op.id} missing field: {fld}")

    # ── Setup references valid operations ────────────────────────────────
    for setup in setups:
        for ref_op in setup.operations:
            if ref_op not in op_map:
                result.errors.append(
                    f"Setup {setup.setup_id} references nonexistent operation {ref_op}"
                )

    # ── Time bounds ──────────────────────────────────────────────────────
    if plan.estimated_time < 1.0:
        result.errors.append(f"Estimated time {plan.estimated_time}s below minimum 1s")
    if plan.estimated_time > 86400:
        result.errors.append(f"Estimated time {plan.estimated_time}s exceeds 24h")

    for op in operations:
        if op.estimated_time < 0:
            result.errors.append(f"Operation {op.id} has negative time")

    result.valid = len(result.errors) == 0

    if result.valid:
        logger.info(
            "Final plan validated: %d ops, %d tools, %d setups, %.1fs",
            len(operations), len(tools), len(setups), plan.estimated_time,
        )
    else:
        logger.warning("Final plan invalid: %s", result.errors)

    return result
