"""
RFQ Packet Builder — Request for Quote manufacturing packet.

Assembles a vendor-facing RFQ packet that includes:
  • Manufacturing packet (from documentation/machining_packet_builder)
  • Vendor requirements (certifications, capabilities)
  • Machine requirements
  • Tolerance specifications
  • Lead time estimates
  • Complexity classification
  • Material certification requirements

This is a superset of the machining packet, formatted for vendor review.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ai_service.conversation.context_builder import ConversationContext
from ai_service.documentation.machining_packet_builder import (
    build_machining_packet,
    MachiningPacket,
)

logger = logging.getLogger("ai_service.rfq.rfq_packet_builder")


# ── Constants ─────────────────────────────────────────────────────────────────

_LEAD_TIME_DAYS: dict[str, int] = {
    "SIMPLE": 5,
    "MEDIUM": 10,
    "COMPLEX": 18,
    "EXTREME": 30,
}

_CERTIFICATION_REQUIREMENTS: dict[str, list[str]] = {
    "TITANIUM": ["AS9100", "NADCAP"],
    "TITANIUM_GR5": ["AS9100", "NADCAP"],
    "STAINLESS_304": ["ISO 9001"],
    "STAINLESS_316": ["ISO 9001"],
    "ALUMINUM_7075": ["ISO 9001"],
    "STEEL_4140": ["ISO 9001"],
}

_MACHINE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "CNC_3AXIS": {
        "type": "3-Axis CNC Milling Center",
        "min_travel": "400×300×300 mm",
        "spindle_speed": "10,000 RPM min",
        "tool_changer": "ATC 20+ tools",
    },
    "CNC_5AXIS": {
        "type": "5-Axis CNC Milling Center",
        "min_travel": "500×400×400 mm",
        "spindle_speed": "15,000 RPM min",
        "tool_changer": "ATC 30+ tools",
        "rotary_axes": "A + C or B + C",
    },
    "LATHE": {
        "type": "CNC Turning Center",
        "max_swing": "300 mm",
        "spindle_speed": "4,000 RPM min",
        "turret": "12-station",
    },
    "MILL_TURN": {
        "type": "Mill-Turn Center",
        "min_travel": "300×300 mm",
        "spindle_speed": "8,000 RPM min",
        "live_tooling": True,
    },
}


# ── Response schema ───────────────────────────────────────────────────────────

class VendorRequirements(BaseModel):
    """Requirements a vendor must meet to quote this job."""

    certifications: list[str] = Field(default_factory=list)
    machine_capabilities: dict = Field(default_factory=dict)
    material_certifications: list[str] = Field(default_factory=list)
    inspection_requirements: list[str] = Field(default_factory=list)
    surface_finish_requirements: list[str] = Field(default_factory=list)


class ToleranceSpec(BaseModel):
    """Tolerance specification summary."""

    general_tolerance: str = "±0.1 mm"
    critical_features: list[dict] = Field(default_factory=list)
    surface_finish: str = "Ra 3.2 μm (standard)"
    notes: list[str] = Field(default_factory=list)


class RFQPacket(BaseModel):
    """Complete RFQ packet for vendor submission."""

    # Header
    rfq_id: str = Field(default_factory=lambda: f"RFQ-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}")
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "DRAFT"

    # Part info
    part_name: str = ""
    model_id: str = ""
    version: int = 1

    # Quantity
    quantity: int = Field(1, ge=1)
    lot_size: int = Field(1, ge=1)

    # Complexity
    complexity_class: str = "MEDIUM"
    complexity_score: float = 0.0

    # Lead time
    estimated_lead_time_days: int = 10
    urgency: str = "STANDARD"

    # Manufacturing packet (embedded)
    manufacturing_packet: MachiningPacket | None = None

    # Vendor requirements
    vendor_requirements: VendorRequirements = Field(default_factory=VendorRequirements)

    # Tolerance
    tolerance_spec: ToleranceSpec = Field(default_factory=ToleranceSpec)

    # Machine requirements
    machine_requirements: dict = Field(default_factory=dict)

    # Cost summary
    estimated_unit_cost: float | None = None
    estimated_total_cost: float | None = None

    # Notes
    special_instructions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# ── Public API ────────────────────────────────────────────────────────────────

def build_rfq_packet(
    ctx: ConversationContext,
    *,
    part_name: str = "",
    quantity: int = 1,
    lot_size: int = 1,
    urgency: str = "STANDARD",
    special_instructions: list[str] | None = None,
) -> RFQPacket:
    """
    Build a complete RFQ packet from conversation context.

    Parameters
    ----------
    ctx : ConversationContext
    part_name : str
    quantity : int
    lot_size : int
    urgency : str
        STANDARD | EXPEDITED | RUSH
    special_instructions : list[str] | None

    Returns
    -------
    RFQPacket
    """

    # Build underlying manufacturing packet
    mfg_packet = build_machining_packet(ctx, part_name=part_name)

    # Complexity class
    complexity_class = _classify_complexity(ctx.complexity_score)

    # Lead time
    lead_time = _estimate_lead_time(complexity_class, quantity, urgency)

    # Vendor requirements
    vendor_reqs = _build_vendor_requirements(ctx)

    # Tolerance spec
    tolerance = _build_tolerance_spec(ctx)

    # Machine requirements
    machine_reqs = _MACHINE_REQUIREMENTS.get(
        ctx.machine_type.upper().strip().replace(" ", "_"),
        {"type": ctx.machine_type, "note": "Specific requirements TBD"},
    )

    # Cost
    unit_cost = mfg_packet.cost_breakdown.get("total_cost", 0) if mfg_packet.cost_breakdown else None
    total_cost = unit_cost * quantity if unit_cost else None

    # Notes
    notes: list[str] = []
    if ctx.is_rollback:
        notes.append("Plan is a rollback version — verify against original specifications.")
    if ctx.risks:
        critical = [r for r in ctx.risks if r.severity == "CRITICAL"]
        if critical:
            notes.append(f"{len(critical)} critical manufacturing risk(s) identified — review before quoting.")
    if complexity_class in ("COMPLEX", "EXTREME"):
        notes.append("High-complexity part may require trial machining / first-article inspection.")

    rfq = RFQPacket(
        part_name=part_name,
        model_id=ctx.model_id,
        version=ctx.version,
        quantity=quantity,
        lot_size=lot_size,
        complexity_class=complexity_class,
        complexity_score=ctx.complexity_score,
        estimated_lead_time_days=lead_time,
        urgency=urgency,
        manufacturing_packet=mfg_packet,
        vendor_requirements=vendor_reqs,
        tolerance_spec=tolerance,
        machine_requirements=machine_reqs,
        estimated_unit_cost=round(unit_cost, 2) if unit_cost else None,
        estimated_total_cost=round(total_cost, 2) if total_cost else None,
        special_instructions=special_instructions or [],
        notes=notes,
    )

    logger.info(
        "Built RFQ packet: model=%s qty=%d complexity=%s lead=%d days est=$%.2f",
        ctx.model_id, quantity, complexity_class, lead_time,
        total_cost or 0,
    )
    return rfq


# ── Internal helpers ──────────────────────────────────────────────────────────

def _classify_complexity(score: float) -> str:
    if score < 0.3:
        return "SIMPLE"
    if score < 0.6:
        return "MEDIUM"
    if score < 0.8:
        return "COMPLEX"
    return "EXTREME"


def _estimate_lead_time(complexity_class: str, quantity: int, urgency: str) -> int:
    base = _LEAD_TIME_DAYS.get(complexity_class, 10)

    # Quantity scaling
    if quantity > 100:
        base = int(base * 1.5)
    elif quantity > 10:
        base = int(base * 1.2)

    # Urgency
    if urgency == "RUSH":
        base = max(3, base // 2)
    elif urgency == "EXPEDITED":
        base = max(5, int(base * 0.7))

    return base


def _build_vendor_requirements(ctx: ConversationContext) -> VendorRequirements:
    certs = _CERTIFICATION_REQUIREMENTS.get(ctx.material.upper().strip(), ["ISO 9001"])
    mat_certs = [f"Material Test Report (MTR) for {ctx.material}"]

    inspection = ["Dimensional inspection report"]
    if ctx.complexity_score >= 0.7:
        inspection.append("First Article Inspection (FAI)")
        inspection.append("CMM report for critical dimensions")

    surface = ["Ra 3.2 μm standard"]
    # Check if finishing operations exist
    has_finishing = any("FINISH" in op.type.upper() for op in ctx.operations)
    if has_finishing:
        surface.append("Ra 1.6 μm on finished surfaces")

    machine_caps = _MACHINE_REQUIREMENTS.get(
        ctx.machine_type.upper().strip().replace(" ", "_"),
        {},
    )

    return VendorRequirements(
        certifications=certs,
        machine_capabilities=machine_caps,
        material_certifications=mat_certs,
        inspection_requirements=inspection,
        surface_finish_requirements=surface,
    )


def _build_tolerance_spec(ctx: ConversationContext) -> ToleranceSpec:
    notes: list[str] = []
    critical_features: list[dict] = []

    for f in ctx.features:
        tol = f.get("tolerances", {})
        if tol:
            critical_features.append({
                "feature_id": f.get("id", f.get("feature_id", "?")),
                "type": f.get("type", "UNKNOWN"),
                "tolerances": tol,
            })

    # Default tolerance based on complexity
    if ctx.complexity_score >= 0.7:
        general = "±0.05 mm"
        surface = "Ra 1.6 μm"
        notes.append("Tight tolerances — recommend CNC with probing capability")
    elif ctx.complexity_score >= 0.4:
        general = "±0.1 mm"
        surface = "Ra 3.2 μm"
    else:
        general = "±0.2 mm"
        surface = "Ra 6.3 μm"

    return ToleranceSpec(
        general_tolerance=general,
        critical_features=critical_features,
        surface_finish=surface,
        notes=notes,
    )
