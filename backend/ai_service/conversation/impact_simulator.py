"""
Impact Simulator — simulate hypothetical plan modifications.

Performs a **read-only** impact analysis using Phase B's refinement engine
and validator.  The diff is generated and validated but NEVER applied to the
DB.  Results include:
  • Validated diff
  • Estimated time / cost delta
  • Risk delta
  • Confidence score
  • Summary narrative

This lets users ask "what would happen if …" without side effects.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from ai_service.conversation.context_builder import ConversationContext

logger = logging.getLogger("ai_service.conversation.impact_simulator")


# ── Response schema ───────────────────────────────────────────────────────────

class ImpactResult(BaseModel):
    """Result of a hypothetical impact simulation."""

    valid: bool = Field(False, description="Whether the proposed change is valid")
    change_count: int = Field(0, description="Number of individual changes in the diff")
    estimated_time_delta: float = Field(0.0, description="Time change in seconds (negative=faster)")
    estimated_cost_delta: float | None = Field(None, description="Cost change in USD")
    new_risk_count: int = Field(0, description="Number of NEW risks introduced")
    removed_risk_count: int = Field(0, description="Number of risks mitigated")
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)
    summary: str = Field("", description="Human-readable impact summary")
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    diff_json: dict = Field(default_factory=dict, description="Raw diff for inspection")


# ── Scenario presets ──────────────────────────────────────────────────────────

_SCENARIO_MAP: dict[str, str] = {
    "reduce setups": "Merge setups where possible to reduce part flips. Combine operations that share similar orientations into fewer setups.",
    "minimize time": "Optimize for minimum machining time. Increase feed rates and use aggressive cutting parameters where safe.",
    "minimize cost": "Optimize for minimum cost. Use standard tooling, reduce tool changes, consolidate operations.",
    "use carbide": "Switch all applicable tools to carbide grade for better surface finish and longer tool life.",
    "increase accuracy": "Add finishing passes, reduce stepover, use finer cutting parameters for tighter tolerances.",
    "reduce tool changes": "Consolidate operations to minimize the number of tool changes without compromising quality.",
    "aggressive": "Use aggressive cutting parameters and strategy for maximum throughput.",
    "conservative": "Use conservative cutting parameters prioritizing safety and surface finish.",
}


def _match_scenario(user_message: str) -> str | None:
    """Check if user_message matches a known preset scenario."""
    lower = user_message.lower()
    for key, instruction in _SCENARIO_MAP.items():
        if key in lower:
            return instruction
    return None


# ── Public API ────────────────────────────────────────────────────────────────

async def simulate_impact(
    user_message: str,
    ctx: ConversationContext,
) -> ImpactResult:
    """
    Simulate the impact of a hypothetical plan modification.

    Uses Phase B's refinement engine to generate an LLM diff, validates
    it, and computes estimated deltas — but does NOT persist anything.

    Parameters
    ----------
    user_message : str
        The what-if question, e.g. "What if we reduced setups?"
    ctx : ConversationContext
        Current plan context.

    Returns
    -------
    ImpactResult
        Full impact analysis.
    """

    # Build instruction: use preset or pass through user message
    instruction = _match_scenario(user_message) or user_message

    # ── Reconstruct Phase B objects from context ─────────────────────────
    from ai_service.schemas.machining_plan import (
        MachiningPlanResponse, OperationSpec, SetupSpec, ToolSpec,
        RiskItem, StrategyVariant,
    )
    from ai_service.schemas.planning_context import PlanningContext, FeatureContext

    plan_resp = MachiningPlanResponse(
        plan_id=ctx.plan_id,
        model_id=ctx.model_id,
        material=ctx.material,
        machine_type=ctx.machine_type,
        setups=ctx.setups,
        operations=ctx.operations,
        tools=ctx.tools,
        risks=ctx.risks,
        strategies=ctx.strategies,
        selected_strategy=ctx.selected_strategy,
        version=ctx.version,
    )

    planning_ctx = PlanningContext(
        model_id=ctx.model_id,
        material=ctx.material,
        machine_type=ctx.machine_type,
        features=[
            FeatureContext(
                id=f.get("id", f.get("feature_id", "?")),
                type=f.get("type", "UNKNOWN"),
                dimensions=f.get("dimensions", {}),
                position=f.get("position", {}),
                direction=f.get("direction", {}),
                tolerances=f.get("tolerances", {}),
            )
            for f in ctx.features
        ],
    )

    # ── Generate diff via Phase B refinement engine ──────────────────────
    try:
        from ai_service.chat.refinement_engine import generate_refinement_diff

        result = await generate_refinement_diff(
            user_message=instruction,
            plan=plan_resp,
            context=planning_ctx,
        )
    except Exception as exc:
        logger.warning("Impact simulation LLM call failed: %s", exc)
        return _deterministic_impact(user_message, ctx)

    diff = result.get("diff")
    validation = result.get("validation")
    preview_plan = result.get("preview_plan")
    summary_text = result.get("summary", "")

    if diff is None:
        return _deterministic_impact(user_message, ctx)

    # ── Compute deltas ───────────────────────────────────────────────────
    time_delta = diff.estimated_time_change if diff else 0.0

    # Risk delta
    new_risks = 0
    removed_risks = 0
    if preview_plan:
        old_risk_codes = {r.code for r in ctx.risks}
        new_risk_codes = {r.code for r in preview_plan.risks}
        new_risks = len(new_risk_codes - old_risk_codes)
        removed_risks = len(old_risk_codes - new_risk_codes)

    # Cost delta approximation: time delta × machine rate
    _MACHINE_RATE_PER_SEC = 0.028  # ~$100/hr ÷ 3600
    cost_delta = time_delta * _MACHINE_RATE_PER_SEC if time_delta != 0 else None

    is_valid = validation.valid if validation else False

    return ImpactResult(
        valid=is_valid,
        change_count=diff.change_count if diff else 0,
        estimated_time_delta=time_delta,
        estimated_cost_delta=cost_delta,
        new_risk_count=new_risks,
        removed_risk_count=removed_risks,
        validation_errors=validation.errors if validation else [],
        validation_warnings=validation.warnings if validation else [],
        summary=summary_text or _build_impact_summary(
            time_delta, cost_delta, new_risks, removed_risks, is_valid, diff
        ),
        confidence=diff.confidence if diff else 0.0,
        diff_json=diff.model_dump() if diff else {},
    )


# ── Deterministic fallback (no LLM) ──────────────────────────────────────────

def _deterministic_impact(
    user_message: str,
    ctx: ConversationContext,
) -> ImpactResult:
    """Provide a rule-based impact estimate when LLM is unavailable."""

    lower = user_message.lower()
    time_delta = 0.0
    summary_parts: list[str] = []

    if "reduce setup" in lower or "fewer setup" in lower:
        if len(ctx.setups) > 1:
            time_delta = -30.0 * (len(ctx.setups) - 1)  # save ~30s per eliminated setup
            summary_parts.append(
                f"Reducing from {len(ctx.setups)} to 1 setup could save "
                f"~{abs(time_delta):.0f}s in setup changes."
            )
        else:
            summary_parts.append("Already using a single setup — no reduction possible.")

    elif "carbide" in lower:
        # Carbide typically allows 20% faster cutting
        time_delta = -ctx.cost_time.total_time * 0.20
        summary_parts.append(
            f"Switching to carbide tooling could reduce machining time by "
            f"~{abs(time_delta):.0f}s (~20%) due to higher feed rates."
        )

    elif "minimize time" in lower or "faster" in lower:
        time_delta = -ctx.cost_time.total_time * 0.15
        summary_parts.append(
            f"Aggressive optimization could save ~{abs(time_delta):.0f}s "
            f"(~15%) but may increase tool wear."
        )

    elif "minimize cost" in lower or "cheaper" in lower:
        time_delta = ctx.cost_time.total_time * 0.05  # slightly slower but cheaper tooling
        summary_parts.append(
            "Cost-optimized tooling may add ~5% time but reduces tool cost."
        )

    elif "accuracy" in lower or "precision" in lower or "tolerance" in lower:
        time_delta = ctx.cost_time.total_time * 0.25  # finishing passes add time
        summary_parts.append(
            f"Adding finishing passes could add ~{time_delta:.0f}s (~25%) "
            f"for tighter tolerances."
        )
    else:
        summary_parts.append(
            "Impact estimation requires LLM for complex scenarios. "
            "Try specific requests like 'reduce setups' or 'minimize time'."
        )

    _MACHINE_RATE_PER_SEC = 0.028
    cost_delta = time_delta * _MACHINE_RATE_PER_SEC if time_delta != 0 else None

    return ImpactResult(
        valid=True,
        change_count=0,
        estimated_time_delta=time_delta,
        estimated_cost_delta=cost_delta,
        new_risk_count=0,
        removed_risk_count=0,
        summary=" ".join(summary_parts),
        confidence=0.5,
    )


def _build_impact_summary(
    time_delta: float,
    cost_delta: float | None,
    new_risks: int,
    removed_risks: int,
    valid: bool,
    diff,
) -> str:
    """Build a human-readable impact summary from computed deltas."""
    parts: list[str] = []

    if not valid:
        parts.append("⚠ The proposed modification failed validation.")

    if time_delta < 0:
        parts.append(f"Time saving: ~{abs(time_delta):.0f}s faster.")
    elif time_delta > 0:
        parts.append(f"Time cost: ~{time_delta:.0f}s slower.")
    else:
        parts.append("No significant time change.")

    if cost_delta is not None:
        if cost_delta < 0:
            parts.append(f"Cost saving: ~${abs(cost_delta):.2f}.")
        elif cost_delta > 0:
            parts.append(f"Additional cost: ~${cost_delta:.2f}.")

    if new_risks > 0:
        parts.append(f"Introduces {new_risks} new risk(s).")
    if removed_risks > 0:
        parts.append(f"Mitigates {removed_risks} existing risk(s).")

    if diff and hasattr(diff, "change_count"):
        parts.append(f"Total changes: {diff.change_count}.")

    return " ".join(parts)
