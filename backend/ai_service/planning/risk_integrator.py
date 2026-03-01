"""
Risk Integrator — attaches manufacturability warnings to operations.

Reads manufacturability_flags from PlanningContext and maps them to
the operations that affect the flagged features. Each risk becomes a
RiskItem attached to the plan.

No LLM. Pure deterministic mapping.
"""

from __future__ import annotations

import logging

from ai_service.schemas.planning_context import PlanningContext
from ai_service.schemas.machining_plan import RiskItem
from ai_service.planning.operation_planner import PlannedOperation

logger = logging.getLogger("ai_service.planning.risk_integrator")


def integrate_risks(
    operations: list[PlannedOperation],
    context: PlanningContext,
) -> list[RiskItem]:
    """
    Map manufacturability flags to operations and produce RiskItem list.

    Each flag is matched to operations via affected_feature_ids.
    If a flag has no specific feature IDs, it applies globally.

    Returns:
        List of RiskItem for inclusion in the final plan.
    """
    if not context.manufacturability_flags:
        return []

    # Build operation lookup by feature_id
    op_by_feature: dict[str, list[str]] = {}
    for op in operations:
        op_by_feature.setdefault(op.feature_id, []).append(op.id)

    risks: list[RiskItem] = []

    for flag in context.manufacturability_flags:
        affected_ops: list[str] = []

        if flag.affected_feature_ids:
            for fid in flag.affected_feature_ids:
                affected_ops.extend(op_by_feature.get(fid, []))
        else:
            # Global warning — applies to all operations
            affected_ops = [op.id for op in operations]

        mitigation = _suggest_mitigation(flag.code, flag.severity)

        risks.append(RiskItem(
            code=flag.code,
            severity=flag.severity,
            message=flag.message,
            affected_operation_ids=affected_ops,
            mitigation=mitigation,
        ))

    logger.info(
        "Risk integration: %d flags → %d risk items",
        len(context.manufacturability_flags), len(risks),
    )
    return risks


def _suggest_mitigation(code: str, severity: str) -> str:
    """Deterministic mitigation suggestions by risk code."""
    mitigations: dict[str, str] = {
        "THIN_WALL": "Reduce depth of cut, use climb milling, add support fixture",
        "DEEP_POCKET": "Use shorter tool first, step-down strategy, check chip evacuation",
        "TIGHT_TOLERANCE": "Add finishing pass, use precision tooling, verify thermal compensation",
        "UNDERCUT": "Requires multi-axis or EDM, flag for manual review",
        "DEEP_HOLE": "Use peck drilling cycle, check coolant-through availability",
        "INTERSECTING_FEATURES": "Machine primary feature first, reduce feed at intersection",
        "SMALL_RADIUS": "Verify tool radius capability, consider EDM for tight corners",
        "HIGH_ASPECT_RATIO": "Use tool with maximum stiffness, reduce cutting speed",
    }
    return mitigations.get(code, f"Review {code} condition — manual inspection recommended")
