"""
Context Builder — assembles full ConversationContext from DB + intelligence.

Merges:
  • ManufacturingGeometryReport (from CAD intelligence)
  • Current MachiningPlan (latest or specified version)
  • Selected strategy name
  • Version number
  • Complexity score + manufacturability flags
  • Cost / time summary

The resulting ConversationContext is passed to every LLM call in Phase C
so the model always reasons over real geometry and plan data.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_service.models import MachiningPlan
from ai_service.ingestion import fetch_model_intelligence, adapt_intelligence
from ai_service.schemas.machining_plan import (
    MachiningPlanResponse,
    OperationSpec,
    SetupSpec,
    ToolSpec,
    RiskItem,
    StrategyVariant,
)

logger = logging.getLogger("ai_service.conversation.context_builder")


# ── Structured context objects ────────────────────────────────────────────────

class CostTimeSummary(BaseModel):
    """Lightweight cost / time snapshot embedded in context."""

    total_time: float = Field(0.0, description="Total estimated machining time (seconds)")
    total_cost: float | None = Field(None, description="Total estimated cost (USD, if available)")
    operation_count: int = 0
    tool_count: int = 0
    setup_count: int = 0


class ConversationContext(BaseModel):
    """
    Single structured object containing everything the LLM needs to answer
    manufacturing questions accurately.
    """

    # ── Identity ─────────────────────────────────────────────────────────
    model_id: str
    plan_id: str | None = None
    version: int = 1
    selected_strategy: str = "CONSERVATIVE"

    # ── Geometry ─────────────────────────────────────────────────────────
    material: str = ""
    machine_type: str = ""
    complexity_score: float = 0.0
    complexity_level: str = "MEDIUM"
    geometry_summary: dict = Field(default_factory=dict)
    features: list[dict] = Field(default_factory=list)
    datum_candidates: list[dict] = Field(default_factory=list)
    stock_recommendation: dict = Field(default_factory=dict)
    manufacturability_flags: list[dict] = Field(default_factory=list)
    topology_graph: dict = Field(default_factory=dict)

    # ── Plan ─────────────────────────────────────────────────────────────
    setups: list[SetupSpec] = Field(default_factory=list)
    operations: list[OperationSpec] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    strategies: list[StrategyVariant] = Field(default_factory=list)

    # ── Aggregates ───────────────────────────────────────────────────────
    cost_time: CostTimeSummary = Field(default_factory=CostTimeSummary)

    # ── Flags ────────────────────────────────────────────────────────────
    is_rollback: bool = False
    approval_status: str = "DRAFT"


# ── Public API ────────────────────────────────────────────────────────────────

async def build_conversation_context(
    model_id: str,
    session: AsyncSession,
    *,
    version: int | None = None,
    plan_id: str | None = None,
) -> ConversationContext:
    """
    Assemble a full ConversationContext from the DB + CAD intelligence API.

    Parameters
    ----------
    model_id : str
        The CAD model ID.
    session : AsyncSession
        Active DB session.
    version : int | None
        Specific version to load.  ``None`` = latest.
    plan_id : str | None
        If provided, load this exact plan row instead of by model_id + version.

    Returns
    -------
    ConversationContext
        Fully populated context ready for LLM or deterministic handlers.
    """

    # ── 1. Fetch plan row ────────────────────────────────────────────────
    plan_row: MachiningPlan | None = None

    if plan_id:
        plan_row = await session.get(MachiningPlan, plan_id)
    elif version is not None:
        result = await session.execute(
            select(MachiningPlan)
            .where(MachiningPlan.model_id == model_id, MachiningPlan.version == version)
            .limit(1)
        )
        plan_row = result.scalar_one_or_none()
    else:
        result = await session.execute(
            select(MachiningPlan)
            .where(MachiningPlan.model_id == model_id)
            .order_by(MachiningPlan.version.desc())
            .limit(1)
        )
        plan_row = result.scalar_one_or_none()

    # ── 2. Parse plan data ───────────────────────────────────────────────
    plan_resp: MachiningPlanResponse | None = None
    if plan_row and plan_row.plan_data:
        try:
            plan_resp = MachiningPlanResponse(**plan_row.plan_data)
        except Exception:
            logger.warning("Could not parse plan_data for plan %s", plan_row.id)

    # ── 3. Fetch intelligence from CAD Service ───────────────────────────
    report: dict[str, Any] = {}
    try:
        intel = await fetch_model_intelligence(model_id)
        report = intel.manufacturing_geometry_report or {}
    except Exception as exc:
        logger.warning("Intelligence unavailable for model %s: %s", model_id, exc)

    # ── 4. Extract geometry sub-sections ─────────────────────────────────
    features_raw = report.get("features", [])
    complexity_raw = report.get("complexity_score", {})
    complexity_value = complexity_raw.get("value", 0.0) if isinstance(complexity_raw, dict) else 0.0
    complexity_level = complexity_raw.get("level", "MEDIUM") if isinstance(complexity_raw, dict) else "MEDIUM"

    # ── 5. Build cost / time summary ─────────────────────────────────────
    cost_time = CostTimeSummary(
        total_time=plan_row.estimated_time if plan_row else 0.0,
        operation_count=len(plan_resp.operations) if plan_resp else 0,
        tool_count=len(plan_resp.tools) if plan_resp else 0,
        setup_count=len(plan_resp.setups) if plan_resp else 0,
    )

    # ── 6. Assemble ──────────────────────────────────────────────────────
    # datum_candidates may be a dict (from intelligence report) or a list
    raw_datum = report.get("datum_candidates", [])
    if isinstance(raw_datum, dict):
        datum_list = [raw_datum]          # wrap single dict into list
    elif isinstance(raw_datum, list):
        datum_list = raw_datum
    else:
        datum_list = []

    ctx = ConversationContext(
        model_id=model_id,
        plan_id=plan_row.id if plan_row else None,
        version=plan_row.version if plan_row else 1,
        selected_strategy=(plan_resp.selected_strategy if plan_resp else "CONSERVATIVE"),
        material=plan_row.material if plan_row else "",
        machine_type=plan_row.machine_type if plan_row else "",
        complexity_score=complexity_value,
        complexity_level=complexity_level,
        geometry_summary=report.get("geometry_summary", {}),
        features=[f if isinstance(f, dict) else {} for f in features_raw],
        datum_candidates=datum_list,
        stock_recommendation=report.get("stock_recommendation", {}),
        manufacturability_flags=report.get("manufacturability_analysis", {}).get("issues", [])
            if isinstance(report.get("manufacturability_analysis"), dict) else [],
        topology_graph=report.get("topology_graph", {}),
        setups=plan_resp.setups if plan_resp else [],
        operations=plan_resp.operations if plan_resp else [],
        tools=plan_resp.tools if plan_resp else [],
        risks=plan_resp.risks if plan_resp else [],
        strategies=plan_resp.strategies if plan_resp else [],
        cost_time=cost_time,
        is_rollback=getattr(plan_row, "is_rollback", False) if plan_row else False,
        approval_status=getattr(plan_row, "approval_status", "DRAFT") if plan_row else "DRAFT",
    )

    logger.info(
        "Built conversation context for model=%s plan=%s v%d "
        "(features=%d, ops=%d, complexity=%.2f)",
        model_id, ctx.plan_id, ctx.version,
        len(ctx.features), len(ctx.operations), ctx.complexity_score,
    )
    return ctx
