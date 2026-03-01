"""
Cost Estimator — deterministic manufacturing cost model.

Computes cost breakdown:
  • Machining cost   = machine_rate × machining_time
  • Tooling cost     = tool_wear_factor × time × number_of_tools
  • Material cost    = stock_volume × material_cost_per_mm³
  • Setup cost       = setup_time × operator_rate
  • Overhead         = flat percentage on top

All values deterministic.  No LLM.
"""

from __future__ import annotations

import logging
import math

from pydantic import BaseModel, Field

from ai_service.conversation.context_builder import ConversationContext
from ai_service.costing.time_simulator import (
    simulate_detailed_time,
    DetailedTimeBreakdown,
)

logger = logging.getLogger("ai_service.costing.cost_estimator")


# ── Rate tables (USD) ────────────────────────────────────────────────────────

# Machine hourly rates
_MACHINE_RATE: dict[str, float] = {
    "CNC_3AXIS": 85.0,
    "CNC_5AXIS": 150.0,
    "LATHE": 70.0,
    "MILL_TURN": 130.0,
    "MANUAL_MILL": 50.0,
    "MANUAL_LATHE": 45.0,
}
_DEFAULT_MACHINE_RATE = 90.0  # $/hr

# Operator rate for setup
_OPERATOR_RATE = 55.0  # $/hr

# Tool wear cost per cutting-minute per tool
_TOOL_WEAR_PER_MIN = 0.08  # $/min — covers insert/bit depreciation

# Material cost per cubic centimetre (cc = 1000 mm³)
_MATERIAL_COST_PER_CC: dict[str, float] = {
    "ALUMINUM": 0.008,
    "ALUMINUM_6061": 0.009,
    "ALUMINUM_7075": 0.012,
    "STEEL": 0.025,
    "STEEL_1045": 0.024,
    "STEEL_4140": 0.030,
    "STAINLESS_304": 0.045,
    "STAINLESS_316": 0.055,
    "TITANIUM": 0.150,
    "TITANIUM_GR5": 0.180,
    "PLASTIC": 0.005,
    "DELRIN": 0.007,
    "NYLON": 0.005,
    "ABS": 0.004,
}
_DEFAULT_MATERIAL_COST = 0.020  # $/cc

# Overhead percentage
_OVERHEAD_PCT = 0.12  # 12%


# ── Response schema ───────────────────────────────────────────────────────────

class CostLineItem(BaseModel):
    """One line item in the cost breakdown."""

    category: str
    description: str
    amount: float = Field(0.0, description="Cost in USD")
    unit: str = "USD"


class CostBreakdown(BaseModel):
    """Full manufacturing cost estimate."""

    model_id: str
    plan_id: str | None = None
    version: int = 1
    strategy: str = "CONSERVATIVE"
    material: str = ""
    machine_type: str = ""

    # Individual cost categories
    machining_cost: float = Field(0.0, description="Machine time × rate (USD)")
    tooling_cost: float = Field(0.0, description="Tool wear + depreciation (USD)")
    material_cost: float = Field(0.0, description="Raw stock material (USD)")
    setup_cost: float = Field(0.0, description="Setup / fixturing labor (USD)")
    overhead_cost: float = Field(0.0, description="Shop overhead (USD)")

    # Grand total
    total_cost: float = Field(0.0, description="Sum of all cost categories (USD)")

    # Breakdown table
    line_items: list[CostLineItem] = Field(default_factory=list)

    # Supporting data
    total_time_seconds: float = 0.0
    total_time_minutes: float = 0.0
    machine_rate_per_hour: float = 0.0
    notes: list[str] = Field(default_factory=list)


# ── Public API ────────────────────────────────────────────────────────────────

def estimate_manufacturing_cost(
    ctx: ConversationContext,
    time_breakdown: DetailedTimeBreakdown | None = None,
) -> CostBreakdown:
    """
    Estimate total manufacturing cost from context + time simulation.

    Parameters
    ----------
    ctx : ConversationContext
    time_breakdown : DetailedTimeBreakdown | None
        Pre-computed time breakdown.  Computed on-the-fly if not provided.

    Returns
    -------
    CostBreakdown
    """
    if time_breakdown is None:
        time_breakdown = simulate_detailed_time(ctx)

    machine_rate = _get_machine_rate(ctx.machine_type)
    items: list[CostLineItem] = []
    notes: list[str] = []

    # ── 1. Machining cost ────────────────────────────────────────────────
    cutting_hours = time_breakdown.total_cutting_time / 3600.0
    machining_cost = cutting_hours * machine_rate
    items.append(CostLineItem(
        category="Machining",
        description=f"{cutting_hours:.2f} hrs × ${machine_rate:.0f}/hr",
        amount=round(machining_cost, 2),
    ))

    # ── 2. Tooling cost ──────────────────────────────────────────────────
    cutting_min = time_breakdown.total_cutting_time / 60.0
    n_tools = len(ctx.tools)
    tooling_cost = cutting_min * _TOOL_WEAR_PER_MIN * max(1, n_tools)
    items.append(CostLineItem(
        category="Tooling",
        description=f"{cutting_min:.1f} min × ${_TOOL_WEAR_PER_MIN}/min × {n_tools} tools",
        amount=round(tooling_cost, 2),
    ))

    # ── 3. Material cost ─────────────────────────────────────────────────
    stock_vol_cc = _estimate_stock_volume_cc(ctx)
    mat_rate = _MATERIAL_COST_PER_CC.get(ctx.material.upper().strip(), _DEFAULT_MATERIAL_COST)
    material_cost = stock_vol_cc * mat_rate
    items.append(CostLineItem(
        category="Material",
        description=f"{stock_vol_cc:.1f} cc × ${mat_rate:.4f}/cc ({ctx.material})",
        amount=round(material_cost, 2),
    ))

    # ── 4. Setup cost ────────────────────────────────────────────────────
    setup_hours = time_breakdown.total_setup_time / 3600.0
    setup_cost = setup_hours * _OPERATOR_RATE
    items.append(CostLineItem(
        category="Setup",
        description=f"{setup_hours:.2f} hrs × ${_OPERATOR_RATE:.0f}/hr operator",
        amount=round(setup_cost, 2),
    ))

    # ── 5. Overhead ──────────────────────────────────────────────────────
    subtotal = machining_cost + tooling_cost + material_cost + setup_cost
    overhead_cost = subtotal * _OVERHEAD_PCT
    items.append(CostLineItem(
        category="Overhead",
        description=f"{_OVERHEAD_PCT * 100:.0f}% of subtotal (${subtotal:.2f})",
        amount=round(overhead_cost, 2),
    ))

    total = subtotal + overhead_cost

    # ── Notes ─────────────────────────────────────────────────────────────
    if ctx.complexity_score >= 0.7:
        notes.append("High complexity may require additional inspection time not included.")
    if len(ctx.setups) > 2:
        notes.append(f"{len(ctx.setups)} setups increase fixturing cost significantly.")
    if ctx.risks:
        critical = [r for r in ctx.risks if r.severity == "CRITICAL"]
        if critical:
            notes.append(f"{len(critical)} critical risk(s) may increase scrap rate / cost.")

    result = CostBreakdown(
        model_id=ctx.model_id,
        plan_id=ctx.plan_id,
        version=ctx.version,
        strategy=ctx.selected_strategy,
        material=ctx.material,
        machine_type=ctx.machine_type,
        machining_cost=round(machining_cost, 2),
        tooling_cost=round(tooling_cost, 2),
        material_cost=round(material_cost, 2),
        setup_cost=round(setup_cost, 2),
        overhead_cost=round(overhead_cost, 2),
        total_cost=round(total, 2),
        line_items=items,
        total_time_seconds=time_breakdown.total_time,
        total_time_minutes=time_breakdown.total_time_minutes,
        machine_rate_per_hour=machine_rate,
        notes=notes,
    )

    logger.info(
        "Cost estimate: model=%s total=$%.2f (machining=$%.2f tooling=$%.2f "
        "material=$%.2f setup=$%.2f overhead=$%.2f)",
        ctx.model_id, total, machining_cost, tooling_cost,
        material_cost, setup_cost, overhead_cost,
    )
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_machine_rate(machine_type: str) -> float:
    """Lookup machine hourly rate."""
    upper = machine_type.upper().strip().replace(" ", "_")
    # Try exact match, then prefix match
    if upper in _MACHINE_RATE:
        return _MACHINE_RATE[upper]
    for key, rate in _MACHINE_RATE.items():
        if key in upper or upper in key:
            return rate
    return _DEFAULT_MACHINE_RATE


def _estimate_stock_volume_cc(ctx: ConversationContext) -> float:
    """Estimate stock billet volume in cubic centimeters."""
    stock = ctx.stock_recommendation
    if not stock:
        return 100.0  # fallback 100 cc

    # Extract dimensions from stock recommendation
    dims = stock.get("dimensions", stock)
    dx = dims.get("x", dims.get("dx", dims.get("length", 0)))
    dy = dims.get("y", dims.get("dy", dims.get("width", 0)))
    dz = dims.get("z", dims.get("dz", dims.get("height", 0)))

    if dx and dy and dz:
        vol_mm3 = float(dx) * float(dy) * float(dz)
        return vol_mm3 / 1000.0  # mm³ → cc

    # Try diameter + length for turning stock
    diameter = dims.get("diameter", 0)
    length = dims.get("length", 0)
    if diameter and length:
        r = float(diameter) / 2.0
        vol_mm3 = math.pi * r * r * float(length)
        return vol_mm3 / 1000.0

    return 100.0  # fallback
