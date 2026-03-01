"""
Detailed Time Simulator — extends Phase B time_estimator with
setup-change penalties, tool-change penalties, roughing/finishing
multipliers, strategy multipliers, and complexity multipliers.

All values are deterministic.  No LLM.  No simulation.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from ai_service.conversation.context_builder import ConversationContext
from ai_service.services.time_estimator import estimate_operation_time

logger = logging.getLogger("ai_service.costing.time_simulator")


# ── Constants ─────────────────────────────────────────────────────────────────

# Setup change overhead (seconds) — fixture swap, re-indicate, zero
SETUP_CHANGE_PENALTY: float = 120.0  # 2 minutes per additional setup

# Tool change overhead (seconds) — ATC or manual
TOOL_CHANGE_PENALTY: float = 15.0  # 15 s per tool change

# First-part setup (fixture, zero, probe)
FIRST_SETUP_TIME: float = 300.0  # 5 min base

# Strategy multipliers applied to pure cutting time
_STRATEGY_MULTIPLIER: dict[str, float] = {
    "CONSERVATIVE": 1.15,   # 15% slower for safety
    "OPTIMIZED": 1.00,      # baseline
    "AGGRESSIVE": 0.85,     # 15% faster, higher risk
}

# Complexity multiplier — extra time for complex parts (nested features, tight tolerances)
_COMPLEXITY_BANDS: list[tuple[float, float]] = [
    (0.0, 0.3, ),   # simple   → 1.0
    (0.3, 0.6, ),   # medium   → 1.1
    (0.6, 0.8, ),   # complex  → 1.25
    (0.8, 1.0, ),   # extreme  → 1.4
]

def _complexity_multiplier(score: float) -> float:
    if score < 0.3:
        return 1.0
    if score < 0.6:
        return 1.10
    if score < 0.8:
        return 1.25
    return 1.40


# Roughing / finishing multiplier (already handled by Phase B time_estimator,
# but we add a small correction for chip-to-chip time)
_ROUGHING_OVERHEAD: float = 1.05   # 5% overhead for chip management
_FINISHING_OVERHEAD: float = 1.10  # 10% overhead for precision passes


# ── Response schema ───────────────────────────────────────────────────────────

class OperationTimeDetail(BaseModel):
    """Time breakdown for a single operation."""

    operation_id: str
    operation_type: str
    feature_id: str
    tool_id: str
    base_time: float = Field(0.0, description="Raw cutting time (s)")
    roughing_finishing_factor: float = Field(1.0, description="R/F multiplier applied")
    strategy_factor: float = Field(1.0, description="Strategy multiplier applied")
    complexity_factor: float = Field(1.0, description="Complexity multiplier applied")
    adjusted_time: float = Field(0.0, description="Final time after all multipliers (s)")


class DetailedTimeBreakdown(BaseModel):
    """Complete time breakdown for the plan."""

    model_id: str
    plan_id: str | None = None
    version: int = 1
    strategy: str = "CONSERVATIVE"

    # Setup times
    first_setup_time: float = Field(FIRST_SETUP_TIME, description="Initial setup (s)")
    setup_change_count: int = Field(0, description="Number of additional setup changes")
    total_setup_time: float = Field(0.0, description="All setup time (s)")

    # Tool change times
    tool_change_count: int = Field(0, description="Number of tool changes")
    total_tool_change_time: float = Field(0.0, description="All tool change time (s)")

    # Cutting times
    total_cutting_time: float = Field(0.0, description="Sum of adjusted op times (s)")
    operation_details: list[OperationTimeDetail] = Field(default_factory=list)

    # Multipliers used
    strategy_multiplier: float = 1.0
    complexity_multiplier: float = 1.0
    complexity_score: float = 0.0

    # Grand total
    total_time: float = Field(0.0, description="Grand total time (s)")
    total_time_minutes: float = Field(0.0, description="Grand total time (min)")


# ── Public API ────────────────────────────────────────────────────────────────

def simulate_detailed_time(ctx: ConversationContext) -> DetailedTimeBreakdown:
    """
    Compute a detailed time breakdown from the conversation context.

    Extends Phase B's ``estimate_operation_time`` with:
      • Setup change penalties
      • Tool change penalties
      • Strategy multiplier
      • Complexity multiplier
      • Roughing/finishing corrections

    Returns
    -------
    DetailedTimeBreakdown
    """

    strategy_mult = _STRATEGY_MULTIPLIER.get(ctx.selected_strategy, 1.0)
    complexity_mult = _complexity_multiplier(ctx.complexity_score)

    # ── Count tool changes ───────────────────────────────────────────────
    tool_change_count = _count_tool_changes(ctx)

    # ── Per-operation detail ─────────────────────────────────────────────
    op_details: list[OperationTimeDetail] = []
    total_cutting = 0.0

    tool_map: dict[str, Any] = {}
    for t in ctx.tools:
        tool_map[t.id] = t

    for op in ctx.operations:
        tool = tool_map.get(op.tool_id)
        tool_type = tool.type if tool else "FLAT_END_MILL"
        tool_diameter = tool.diameter if tool else 10.0

        # Base time from Phase B estimator
        base_time = op.estimated_time
        if base_time <= 0:
            base_time = estimate_operation_time(
                op_type=op.type,
                tool_type=tool_type,
                tool_diameter=tool_diameter,
                material=ctx.material,
                parameters=op.parameters,
            )

        # Roughing / finishing factor
        rf_factor = 1.0
        if "ROUGH" in op.type.upper():
            rf_factor = _ROUGHING_OVERHEAD
        elif "FINISH" in op.type.upper():
            rf_factor = _FINISHING_OVERHEAD

        adjusted = base_time * rf_factor * strategy_mult * complexity_mult
        total_cutting += adjusted

        op_details.append(OperationTimeDetail(
            operation_id=op.id,
            operation_type=op.type,
            feature_id=op.feature_id,
            tool_id=op.tool_id,
            base_time=round(base_time, 2),
            roughing_finishing_factor=rf_factor,
            strategy_factor=strategy_mult,
            complexity_factor=complexity_mult,
            adjusted_time=round(adjusted, 2),
        ))

    # ── Setup time ───────────────────────────────────────────────────────
    setup_changes = max(0, len(ctx.setups) - 1)
    total_setup = FIRST_SETUP_TIME + setup_changes * SETUP_CHANGE_PENALTY

    # ── Tool change time ─────────────────────────────────────────────────
    total_tool_change = tool_change_count * TOOL_CHANGE_PENALTY

    # ── Grand total ──────────────────────────────────────────────────────
    grand_total = total_cutting + total_setup + total_tool_change

    result = DetailedTimeBreakdown(
        model_id=ctx.model_id,
        plan_id=ctx.plan_id,
        version=ctx.version,
        strategy=ctx.selected_strategy,
        first_setup_time=FIRST_SETUP_TIME,
        setup_change_count=setup_changes,
        total_setup_time=round(total_setup, 2),
        tool_change_count=tool_change_count,
        total_tool_change_time=round(total_tool_change, 2),
        total_cutting_time=round(total_cutting, 2),
        operation_details=op_details,
        strategy_multiplier=strategy_mult,
        complexity_multiplier=complexity_mult,
        complexity_score=ctx.complexity_score,
        total_time=round(grand_total, 2),
        total_time_minutes=round(grand_total / 60, 2),
    )

    logger.info(
        "Time simulation: model=%s total=%.1fs (cutting=%.1fs setup=%.1fs tool_chg=%.1fs)",
        ctx.model_id, grand_total, total_cutting, total_setup, total_tool_change,
    )
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _count_tool_changes(ctx: ConversationContext) -> int:
    """Count the number of tool changes in the operation sequence."""
    if not ctx.operations:
        return 0

    changes = 0
    prev_tool = None
    for op in ctx.operations:
        if prev_tool is not None and op.tool_id != prev_tool:
            changes += 1
        prev_tool = op.tool_id
    return changes
