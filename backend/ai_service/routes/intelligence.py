"""
Phase C routes — Conversational Manufacturing Intelligence.

Endpoints:
    POST /intelligence/{model_id}/query           — Conversational query
    GET  /intelligence/{model_id}/cost             — Cost breakdown
    GET  /intelligence/{model_id}/time             — Time breakdown
    GET  /intelligence/{model_id}/spatial           — Spatial operation map
    GET  /intelligence/{model_id}/packet            — Manufacturing packet (JSON)
    POST /intelligence/{model_id}/rfq               — RFQ packet
    POST /intelligence/{model_id}/industrial-pdf     — Industrial PDF report
    POST /intelligence/{model_id}/impact             — Impact simulation
    GET  /intelligence/{model_id}/explain/feature/{fid}     — Feature explanation
    GET  /intelligence/{model_id}/explain/operation/{oid}   — Operation explanation
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import get_session
from ai_service.services.conversational_service import handle_conversational_query

logger = logging.getLogger("ai_service.routes.intelligence")

intelligence_router = APIRouter(prefix="/intelligence", tags=["intelligence"])


# ── Request / Response schemas ────────────────────────────────────────────────

class IntelligenceQueryRequest(BaseModel):
    """Request for the conversational query endpoint."""

    user_message: str = Field(
        ..., min_length=1, max_length=2000,
        description="Natural language query about the machining plan",
    )
    plan_id: str | None = Field(None, description="Specific plan row ID (optional)")
    version: int | None = Field(None, ge=1, description="Specific version (optional)")
    part_name: str = Field("", description="Human-readable part name")


class IntelligenceResponse(BaseModel):
    """Unified response from all intelligence endpoints."""

    type: str = Field(..., description="Response type identifier")
    data: Any = Field(default=None, description="Structured data payload")
    message: str = Field("", description="Human-readable summary")


class ImpactRequest(BaseModel):
    """Request for impact simulation."""

    scenario: str = Field(
        ..., min_length=1, max_length=2000,
        description="What-if scenario description",
    )
    plan_id: str | None = None
    version: int | None = None


class RFQRequest(BaseModel):
    """Request for RFQ packet generation."""

    part_name: str = ""
    quantity: int = Field(1, ge=1)
    lot_size: int = Field(1, ge=1)
    urgency: str = Field("STANDARD", description="STANDARD | EXPEDITED | RUSH")
    special_instructions: list[str] = Field(default_factory=list)
    plan_id: str | None = None
    version: int | None = None


class IndustrialPDFRequest(BaseModel):
    """Request for industrial PDF generation."""

    part_name: str = "Unnamed Part"
    company_name: str = "MechAI Manufacturing"
    include_cost: bool = True
    include_time_breakdown: bool = True
    include_risk_assessment: bool = True
    include_strategy_comparison: bool = True
    include_revision_history: bool = True
    plan_id: str | None = None
    version: int | None = None


# ── Conversational Query ──────────────────────────────────────────────────────

@intelligence_router.post(
    "/{model_id}/query",
    response_model=IntelligenceResponse,
    summary="Conversational manufacturing intelligence query",
    description=(
        "Ask any question about the machining plan. "
        "Routes automatically to the appropriate handler: "
        "general queries, explanations, impact simulation, "
        "cost/time breakdown, or LLM conversation."
    ),
)
async def query(
    model_id: str,
    req: IntelligenceQueryRequest,
    session: AsyncSession = Depends(get_session),
) -> IntelligenceResponse:
    result = await handle_conversational_query(
        user_message=req.user_message,
        model_id=model_id,
        session=session,
        plan_id=req.plan_id,
        version=req.version,
        part_name=req.part_name,
    )
    return IntelligenceResponse(
        type=result.get("type", "conversation"),
        data=result.get("data"),
        message=result.get("message", ""),
    )


# ── Cost Breakdown ────────────────────────────────────────────────────────────

@intelligence_router.get(
    "/{model_id}/cost",
    response_model=IntelligenceResponse,
    summary="Get detailed cost breakdown",
)
async def cost_breakdown(
    model_id: str,
    version: int | None = Query(None, ge=1),
    plan_id: str | None = Query(None),
    strategy: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> IntelligenceResponse:
    result = await handle_conversational_query(
        user_message=f"cost breakdown{' for ' + strategy + ' strategy' if strategy else ''}",
        model_id=model_id,
        session=session,
        plan_id=plan_id,
        version=version,
    )
    return IntelligenceResponse(
        type=result.get("type", "cost_breakdown"),
        data=result.get("data"),
        message=result.get("message", ""),
    )


# ── Time Breakdown ────────────────────────────────────────────────────────────

@intelligence_router.get(
    "/{model_id}/time",
    response_model=IntelligenceResponse,
    summary="Get detailed time breakdown",
)
async def time_breakdown(
    model_id: str,
    version: int | None = Query(None, ge=1),
    plan_id: str | None = Query(None),
    strategy: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> IntelligenceResponse:
    result = await handle_conversational_query(
        user_message=f"time breakdown{' for ' + strategy + ' strategy' if strategy else ''}",
        model_id=model_id,
        session=session,
        plan_id=plan_id,
        version=version,
    )
    return IntelligenceResponse(
        type=result.get("type", "time_breakdown"),
        data=result.get("data"),
        message=result.get("message", ""),
    )


# ── Spatial Operation Map ─────────────────────────────────────────────────────

@intelligence_router.get(
    "/{model_id}/spatial",
    response_model=IntelligenceResponse,
    summary="Get spatial operation map (3D coordinates, tool axes)",
)
async def spatial_map(
    model_id: str,
    version: int | None = Query(None, ge=1),
    plan_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> IntelligenceResponse:
    result = await handle_conversational_query(
        user_message="spatial map",
        model_id=model_id,
        session=session,
        plan_id=plan_id,
        version=version,
    )
    return IntelligenceResponse(
        type=result.get("type", "spatial_map"),
        data=result.get("data"),
        message=result.get("message", ""),
    )


# ── Manufacturing Packet ──────────────────────────────────────────────────────

@intelligence_router.get(
    "/{model_id}/packet",
    response_model=IntelligenceResponse,
    summary="Get structured manufacturing packet (JSON)",
)
async def manufacturing_packet(
    model_id: str,
    part_name: str = Query("", description="Part name for the packet"),
    version: int | None = Query(None, ge=1),
    plan_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> IntelligenceResponse:
    result = await handle_conversational_query(
        user_message="manufacturing packet",
        model_id=model_id,
        session=session,
        plan_id=plan_id,
        version=version,
        part_name=part_name,
    )
    return IntelligenceResponse(
        type=result.get("type", "machining_packet"),
        data=result.get("data"),
        message=result.get("message", ""),
    )


# ── RFQ Packet ────────────────────────────────────────────────────────────────

@intelligence_router.post(
    "/{model_id}/rfq",
    response_model=IntelligenceResponse,
    summary="Generate RFQ (Request for Quote) vendor packet",
)
async def rfq_packet(
    model_id: str,
    req: RFQRequest,
    session: AsyncSession = Depends(get_session),
) -> IntelligenceResponse:
    from ai_service.conversation.context_builder import build_conversation_context
    from ai_service.rfq.rfq_packet_builder import build_rfq_packet

    ctx = await build_conversation_context(
        model_id, session,
        version=req.version,
        plan_id=req.plan_id,
    )
    rfq = build_rfq_packet(
        ctx,
        part_name=req.part_name,
        quantity=req.quantity,
        lot_size=req.lot_size,
        urgency=req.urgency,
        special_instructions=req.special_instructions,
    )
    return IntelligenceResponse(
        type="rfq_packet",
        data=rfq.model_dump(),
        message=(
            f"RFQ packet generated: {rfq.complexity_class} complexity, "
            f"est. lead time {rfq.estimated_lead_time_days} days, "
            f"est. cost ${rfq.estimated_total_cost or 0:.2f}."
        ),
    )


# ── Industrial PDF ────────────────────────────────────────────────────────────

@intelligence_router.post(
    "/{model_id}/industrial-pdf",
    summary="Generate industrial machining report PDF",
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Industrial PDF report",
        }
    },
)
async def industrial_pdf(
    model_id: str,
    req: IndustrialPDFRequest,
    session: AsyncSession = Depends(get_session),
) -> Response:
    from ai_service.conversation.context_builder import build_conversation_context
    from ai_service.documentation.pdf_generator import (
        generate_industrial_pdf,
        IndustrialPDFConfig,
    )

    ctx = await build_conversation_context(
        model_id, session,
        version=req.version,
        plan_id=req.plan_id,
    )

    config = IndustrialPDFConfig(
        company_name=req.company_name,
        part_name=req.part_name,
        include_cost=req.include_cost,
        include_time_breakdown=req.include_time_breakdown,
        include_risk_assessment=req.include_risk_assessment,
        include_strategy_comparison=req.include_strategy_comparison,
        include_revision_history=req.include_revision_history,
    )

    # Fetch revision history if requested
    revision_history = None
    if req.include_revision_history:
        from sqlalchemy import select
        from ai_service.models import MachiningPlan
        result = await session.execute(
            select(MachiningPlan)
            .where(MachiningPlan.model_id == model_id)
            .order_by(MachiningPlan.version.asc())
        )
        rows = result.scalars().all()
        revision_history = [
            {
                "version": r.version,
                "created_at": str(r.created_at),
                "selected_strategy": (r.plan_data or {}).get("selected_strategy", "?"),
                "is_rollback": getattr(r, "is_rollback", False),
                "approval_status": getattr(r, "approval_status", "DRAFT"),
            }
            for r in rows
        ]

    pdf_bytes = generate_industrial_pdf(ctx, config, revision_history)

    filename = f"industrial_report_{req.part_name.replace(' ', '_')}_v{ctx.version}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Impact Simulation ─────────────────────────────────────────────────────────

@intelligence_router.post(
    "/{model_id}/impact",
    response_model=IntelligenceResponse,
    summary="Simulate impact of a hypothetical plan modification",
)
async def impact_simulation(
    model_id: str,
    req: ImpactRequest,
    session: AsyncSession = Depends(get_session),
) -> IntelligenceResponse:
    result = await handle_conversational_query(
        user_message=f"what if {req.scenario}",
        model_id=model_id,
        session=session,
        plan_id=req.plan_id,
        version=req.version,
    )
    return IntelligenceResponse(
        type=result.get("type", "impact_simulation"),
        data=result.get("data"),
        message=result.get("message", ""),
    )


# ── Feature Explanation ───────────────────────────────────────────────────────

@intelligence_router.get(
    "/{model_id}/explain/feature/{feature_id}",
    response_model=IntelligenceResponse,
    summary="Explain a detected feature in detail",
)
async def explain_feature_endpoint(
    model_id: str,
    feature_id: str,
    version: int | None = Query(None, ge=1),
    plan_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> IntelligenceResponse:
    from ai_service.conversation.context_builder import build_conversation_context
    from ai_service.conversation.explanation_engine import explain_feature

    ctx = await build_conversation_context(
        model_id, session, version=version, plan_id=plan_id,
    )
    explanation = await explain_feature(feature_id, ctx)
    return IntelligenceResponse(
        type="feature_explanation",
        data=explanation.model_dump(),
        message=explanation.explanation,
    )


# ── Operation Explanation ─────────────────────────────────────────────────────

@intelligence_router.get(
    "/{model_id}/explain/operation/{operation_id}",
    response_model=IntelligenceResponse,
    summary="Explain a planned operation in detail",
)
async def explain_operation_endpoint(
    model_id: str,
    operation_id: str,
    version: int | None = Query(None, ge=1),
    plan_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> IntelligenceResponse:
    from ai_service.conversation.context_builder import build_conversation_context
    from ai_service.conversation.explanation_engine import explain_operation

    ctx = await build_conversation_context(
        model_id, session, version=version, plan_id=plan_id,
    )
    explanation = await explain_operation(operation_id, ctx)
    return IntelligenceResponse(
        type="operation_explanation",
        data=explanation.model_dump(),
        message=explanation.explanation,
    )


# ── Initial Narrative ─────────────────────────────────────────────────────────

@intelligence_router.get(
    "/{model_id}/narrative",
    response_model=IntelligenceResponse,
    summary="Get initial comprehensive manufacturing narrative",
    description=(
        "Generates a detailed initial explanation of the machining plan "
        "including setup reasoning, operation sequence, tool selection, "
        "strategy explanation, risk assessment, and cost reasoning."
    ),
)
async def initial_narrative(
    model_id: str,
    version: int | None = Query(None, ge=1),
    plan_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> IntelligenceResponse:
    from ai_service.conversation.context_builder import build_conversation_context
    from ai_service.conversation.narrative_builder import build_initial_narrative

    ctx = await build_conversation_context(
        model_id, session, version=version, plan_id=plan_id,
    )
    narrative = build_initial_narrative(ctx)
    return IntelligenceResponse(
        type="initial_narrative",
        data=narrative,
        message=narrative.get("full_text", ""),
    )
