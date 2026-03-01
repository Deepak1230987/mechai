"""
Machining Packet Builder — structured JSON manufacturing packet.

Produces a complete, machine-readable JSON packet containing every detail
an operator or downstream system needs:
  • Part identity & material spec
  • Geometry summary (features, complexity)
  • Complete setup plan with orientation + datum
  • Ordered operation sequence with full parameters
  • Tool list with cutting parameters
  • Time breakdown
  • Cost breakdown
  • Risk assessment
  • Strategy info
  • Version & approval metadata

This packet is the data backbone for:
  • PDF generation (documentation/pdf_generator.py)
  • RFQ packet builder (rfq/rfq_packet_builder.py)
  • External MES/ERP integration
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ai_service.conversation.context_builder import ConversationContext
from ai_service.costing.time_simulator import simulate_detailed_time, DetailedTimeBreakdown
from ai_service.costing.cost_estimator import estimate_manufacturing_cost, CostBreakdown

logger = logging.getLogger("ai_service.documentation.machining_packet_builder")


# ── Schema ────────────────────────────────────────────────────────────────────

class MachiningPacket(BaseModel):
    """Complete structured manufacturing packet."""

    # Identity
    packet_version: str = Field("1.0", description="Packet schema version")
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_id: str
    plan_id: str | None = None
    version: int = 1

    # Part spec
    material: str = ""
    machine_type: str = ""
    part_name: str = ""

    # Geometry
    feature_count: int = 0
    features: list[dict] = Field(default_factory=list)
    complexity_score: float = 0.0
    complexity_level: str = "MEDIUM"
    geometry_summary: dict = Field(default_factory=dict)
    stock_recommendation: dict = Field(default_factory=dict)

    # Manufacturing plan
    setups: list[dict] = Field(default_factory=list)
    operations: list[dict] = Field(default_factory=list)
    tools: list[dict] = Field(default_factory=list)
    risks: list[dict] = Field(default_factory=list)

    # Strategy
    selected_strategy: str = "CONSERVATIVE"
    strategies: list[dict] = Field(default_factory=list)

    # Time
    time_breakdown: dict = Field(default_factory=dict)

    # Cost
    cost_breakdown: dict = Field(default_factory=dict)

    # Manufacturability
    manufacturability_flags: list[dict] = Field(default_factory=list)
    datum_candidates: list[dict] = Field(default_factory=list)

    # Version metadata
    is_rollback: bool = False
    approval_status: str = "DRAFT"

    # Topology (raw graph for downstream systems)
    topology_graph: dict = Field(default_factory=dict)


# ── Public API ────────────────────────────────────────────────────────────────

def build_machining_packet(
    ctx: ConversationContext,
    *,
    part_name: str = "",
    include_topology: bool = False,
) -> MachiningPacket:
    """
    Build a complete manufacturing packet from conversation context.

    Parameters
    ----------
    ctx : ConversationContext
    part_name : str
        Human-readable part name.
    include_topology : bool
        Whether to include the full topology graph (can be large).

    Returns
    -------
    MachiningPacket
    """

    # Compute time & cost
    time_bd = simulate_detailed_time(ctx)
    cost_bd = estimate_manufacturing_cost(ctx, time_bd)

    packet = MachiningPacket(
        model_id=ctx.model_id,
        plan_id=ctx.plan_id,
        version=ctx.version,
        material=ctx.material,
        machine_type=ctx.machine_type,
        part_name=part_name,
        feature_count=len(ctx.features),
        features=ctx.features,
        complexity_score=ctx.complexity_score,
        complexity_level=ctx.complexity_level,
        geometry_summary=ctx.geometry_summary,
        stock_recommendation=ctx.stock_recommendation,
        setups=[s.model_dump() for s in ctx.setups],
        operations=[
            {
                "id": op.id,
                "feature_id": op.feature_id,
                "type": op.type,
                "tool_id": op.tool_id,
                "parameters": op.parameters,
                "estimated_time": op.estimated_time,
            }
            for op in ctx.operations
        ],
        tools=[
            {
                "id": t.id,
                "type": t.type,
                "diameter": t.diameter,
                "max_depth": t.max_depth,
                "rpm_min": t.recommended_rpm_min,
                "rpm_max": t.recommended_rpm_max,
            }
            for t in ctx.tools
        ],
        risks=[
            {
                "code": r.code,
                "severity": r.severity,
                "message": r.message,
                "affected_operation_ids": r.affected_operation_ids,
                "mitigation": r.mitigation,
            }
            for r in ctx.risks
        ],
        selected_strategy=ctx.selected_strategy,
        strategies=[
            {
                "name": s.name,
                "description": s.description,
                "estimated_time": s.estimated_time,
                "setup_count": s.setup_count,
                "operation_count": s.operation_count,
                "changes_from_base": s.changes_from_base,
            }
            for s in ctx.strategies
        ],
        time_breakdown=time_bd.model_dump(),
        cost_breakdown=cost_bd.model_dump(),
        manufacturability_flags=ctx.manufacturability_flags,
        datum_candidates=ctx.datum_candidates,
        is_rollback=ctx.is_rollback,
        approval_status=ctx.approval_status,
        topology_graph=ctx.topology_graph if include_topology else {},
    )

    logger.info(
        "Built machining packet: model=%s v%d features=%d ops=%d cost=$%.2f",
        ctx.model_id, ctx.version, packet.feature_count,
        len(packet.operations), cost_bd.total_cost,
    )
    return packet
