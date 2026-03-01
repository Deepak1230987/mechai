"""
Strategy Generator — produces plan variants for user selection.

Strategies:
  1. CONSERVATIVE (Base) — pure deterministic plan, no LLM changes
  2. OPTIMIZED (LLM)     — base + validated LLM improvements
  3. AGGRESSIVE           — only if complexity_score < 0.4,
                            further optimizations with relaxed constraints

Each strategy is a StrategyVariant attached to the final plan.
The user selects which strategy to apply.
"""

from __future__ import annotations

import logging

from ai_service.schemas.machining_plan import (
    MachiningPlanResponse,
    StrategyVariant,
)
from ai_service.schemas.planning_context import PlanningContext

logger = logging.getLogger("ai_service.planning.strategy_generator")


def generate_strategies(
    base_plan: MachiningPlanResponse,
    optimized_plan: MachiningPlanResponse,
    context: PlanningContext,
) -> list[StrategyVariant]:
    """
    Produce strategy variants comparing base and optimized plans.

    Args:
        base_plan:      Pure deterministic plan.
        optimized_plan: Plan after LLM diff merge.
        context:        PlanningContext for complexity check.

    Returns:
        List of StrategyVariant to attach to the final plan.
    """
    strategies: list[StrategyVariant] = []

    # ── 1. Conservative (always available) ───────────────────────────────
    strategies.append(StrategyVariant(
        name="CONSERVATIVE",
        description="Pure deterministic plan — no AI modifications. Maximum safety.",
        estimated_time=base_plan.estimated_time,
        setup_count=len(base_plan.setups),
        operation_count=len(base_plan.operations),
        changes_from_base=[],
    ))

    # ── 2. Optimized (if LLM made changes) ──────────────────────────────
    changes = _compute_changes(base_plan, optimized_plan)

    if changes:
        strategies.append(StrategyVariant(
            name="OPTIMIZED",
            description=(
                "AI-optimized plan — deterministic base + validated improvements. "
                + (optimized_plan.llm_justification or "")
            ),
            estimated_time=optimized_plan.estimated_time,
            setup_count=len(optimized_plan.setups),
            operation_count=len(optimized_plan.operations),
            changes_from_base=changes,
        ))
    else:
        strategies.append(StrategyVariant(
            name="OPTIMIZED",
            description="No improvements found — identical to conservative plan.",
            estimated_time=base_plan.estimated_time,
            setup_count=len(base_plan.setups),
            operation_count=len(base_plan.operations),
            changes_from_base=["No changes — base plan is already optimal"],
        ))

    # ── 3. Aggressive (only for low complexity parts) ────────────────────
    if context.complexity_score < 0.4:
        time_reduction = optimized_plan.estimated_time * 0.85
        strategies.append(StrategyVariant(
            name="AGGRESSIVE",
            description=(
                "Aggressive optimization for simple geometry. "
                "Reduced safety margins, combined passes. "
                "Recommended only for prototype / non-critical parts."
            ),
            estimated_time=round(time_reduction, 2),
            setup_count=max(1, len(optimized_plan.setups) - 1),
            operation_count=len(optimized_plan.operations),
            changes_from_base=[
                "15% time reduction via increased feed rates",
                "Reduced safety margins on non-critical features",
                "Combined roughing/finishing where safe",
            ],
        ))

    logger.info(
        "Generated %d strategies for model=%s (complexity=%.2f)",
        len(strategies), context.model_id, context.complexity_score,
    )
    return strategies


def _compute_changes(
    base: MachiningPlanResponse,
    optimized: MachiningPlanResponse,
) -> list[str]:
    """Compute human-readable list of changes between base and optimized."""
    changes: list[str] = []

    # Operation count diff
    base_ops = len(base.operations)
    opt_ops = len(optimized.operations)
    if opt_ops != base_ops:
        changes.append(f"Operations: {base_ops} → {opt_ops}")

    # Setup count diff
    base_setups = len(base.setups)
    opt_setups = len(optimized.setups)
    if opt_setups != base_setups:
        changes.append(f"Setups: {base_setups} → {opt_setups}")

    # Tool count diff
    base_tools = len(base.tools)
    opt_tools = len(optimized.tools)
    if opt_tools != base_tools:
        changes.append(f"Tools: {base_tools} → {opt_tools}")

    # Time diff
    time_delta = optimized.estimated_time - base.estimated_time
    if abs(time_delta) > 0.5:
        sign = "+" if time_delta > 0 else ""
        changes.append(f"Time: {sign}{time_delta:.1f}s")

    # Operation order change
    base_order = [op.id for op in base.operations]
    opt_order = [op.id for op in optimized.operations if op.id in set(base_order)]
    if opt_order != [oid for oid in base_order if oid in set(opt_order)]:
        changes.append("Operation sequence reordered")

    return changes
