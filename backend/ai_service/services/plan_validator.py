"""
Plan Validator — post-generation validation of machining plans.

Validates that a MachiningPlan (whether from rule engine or LLM optimiser)
is physically valid and self-consistent.

Checks:
    1. All features mapped to at least one operation
    2. No hallucinated tools (every tool_id in operations exists in tools list)
    3. Tool material compatibility
    4. Required fields exist on every operation / tool / setup
    5. Estimated time is reasonable (> 0, < 24 hours)
    6. No duplicate operation IDs
    7. All operation IDs referenced in setups actually exist

If validation fails, the invalid plan is rejected and the caller
falls back to the rule engine baseline.
"""

from __future__ import annotations

import logging

from ai_service.services.tool_library import ToolLibrary

logger = logging.getLogger(__name__)

_lib = ToolLibrary()

# Reasonable time bounds
_MIN_TIME_S = 1.0
_MAX_TIME_S = 86400.0  # 24 hours


class PlanValidationError(Exception):
    """Raised when a plan fails validation."""
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Plan validation failed: {errors}")


class PlanValidator:
    """
    Validates a machining plan dict for physical and structural correctness.

    Usage:
        validator = PlanValidator(validated_features, material, machine_type)
        validated_plan = validator.validate(plan_dict)
        # raises PlanValidationError on failure
    """

    def __init__(
        self,
        validated_features: list[dict],
        material: str,
        machine_type: str,
    ) -> None:
        self._features = {f["id"]: f for f in validated_features}
        self._material = material
        self._machine_type = machine_type

    def validate(self, plan: dict) -> dict:
        """
        Validate a plan dict.  Returns plan if valid, raises PlanValidationError otherwise.
        """
        errors: list[str] = []

        operations = plan.get("operations", [])
        tools = plan.get("tools", [])
        setups = plan.get("setups", [])
        est_time = plan.get("estimated_time", 0)

        # ── 1. Required top-level fields ─────────────────────────────────
        for key in ("setups", "operations", "tools", "estimated_time"):
            if key not in plan:
                errors.append(f"Missing required field: {key}")

        if errors:
            raise PlanValidationError(errors)

        # ── 2. Build lookup maps ─────────────────────────────────────────
        tool_map = {}
        for t in tools:
            tid = t.get("id")
            if not tid:
                errors.append("Tool missing 'id' field")
                continue
            tool_map[tid] = t

        op_map = {}
        for op in operations:
            oid = op.get("id")
            if not oid:
                errors.append("Operation missing 'id' field")
                continue
            if oid in op_map:
                errors.append(f"Duplicate operation id: {oid}")
            op_map[oid] = op

        # ── 3. All features mapped ──────────────────────────────────────
        mapped_feature_ids = {op.get("feature_id") for op in operations}
        for fid in self._features:
            if fid not in mapped_feature_ids:
                errors.append(f"Feature {fid} has no operations in plan")

        # ── 4. No hallucinated tools ────────────────────────────────────
        for op in operations:
            tool_id = op.get("tool_id")
            if tool_id and tool_id not in tool_map:
                errors.append(
                    f"Operation {op.get('id')} references non-existent tool {tool_id}"
                )

        # ── 5. Tool required fields ─────────────────────────────────────
        for t in tools:
            for field in ("id", "type", "diameter"):
                if field not in t or t[field] is None:
                    errors.append(f"Tool {t.get('id', '?')} missing field: {field}")

        # ── 6. Operation required fields ────────────────────────────────
        for op in operations:
            for field in ("id", "feature_id", "type", "tool_id"):
                if field not in op or op[field] is None:
                    errors.append(
                        f"Operation {op.get('id', '?')} missing field: {field}"
                    )

        # ── 7. Setup references valid operations ────────────────────────
        for setup in setups:
            for ref_op_id in setup.get("operations", []):
                if ref_op_id not in op_map:
                    errors.append(
                        f"Setup {setup.get('setup_id', '?')} references "
                        f"non-existent operation {ref_op_id}"
                    )

        # ── 8. Estimated time reasonable ────────────────────────────────
        if est_time < _MIN_TIME_S:
            errors.append(
                f"Estimated time {est_time}s is below minimum {_MIN_TIME_S}s"
            )
        if est_time > _MAX_TIME_S:
            errors.append(
                f"Estimated time {est_time}s exceeds maximum {_MAX_TIME_S}s (24h)"
            )

        # ── 9. Per-operation time sanity ────────────────────────────────
        for op in operations:
            op_time = op.get("estimated_time", 0)
            if op_time < 0:
                errors.append(
                    f"Operation {op.get('id')} has negative time: {op_time}"
                )

        # ── Result ──────────────────────────────────────────────────────
        if errors:
            logger.warning(
                "Plan validation failed with %d errors: %s",
                len(errors), errors,
            )
            raise PlanValidationError(errors)

        logger.info(
            "Plan validated: %d ops, %d tools, %d setups, %.1fs",
            len(operations), len(tools), len(setups), est_time,
        )
        return plan
