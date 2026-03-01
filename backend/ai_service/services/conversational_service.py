"""
Conversational Service — Phase C entry point for intelligent queries.

Routes incoming messages to the appropriate handler:
  • General queries   → general_query_handler (deterministic JSON)
  • Explanations      → explanation_engine (feature/operation details)
  • Impact questions   → impact_simulator (what-if analysis)
  • Modifications     → Phase B refinement engine (via redirect signal)
  • PDF / export      → documentation/pdf_generator
  • RFQ               → rfq/rfq_packet_builder
  • Cost / time       → costing/ (detailed breakdown)
  • Visualization     → visualization/operation_mapper (spatial map)
  • Rollback          → Phase B rollback_service (via redirect signal)
  • Conversation      → conversational_engine (LLM + fallback)

This service builds a ConversationContext once and passes it to all handlers.
It does NOT modify the plan — all changes route through Phase B consent flow.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ai_service.conversation.context_builder import (
    build_conversation_context,
    ConversationContext,
)
from ai_service.conversation.general_query_handler import (
    handle_general_query,
    classify_general_query,
)
from ai_service.conversation.conversational_engine import (
    conversational_engine_answer,
    ConversationalAnswer,
)
from ai_service.conversation.impact_simulator import simulate_impact, ImpactResult
from ai_service.conversation.explanation_engine import (
    explain_feature,
    explain_operation,
    FeatureExplanation,
    OperationExplanation,
)

logger = logging.getLogger("ai_service.services.conversational_service")


# ── Query type classification ─────────────────────────────────────────────────

_EXPLAIN_FEATURE_RE = re.compile(
    r"explain\s+feature\s+([a-zA-Z0-9_-]+)|"
    r"what\s+is\s+feature\s+([a-zA-Z0-9_-]+)|"
    r"tell\s+me\s+about\s+feature\s+([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)

_EXPLAIN_OPERATION_RE = re.compile(
    r"explain\s+operation\s+([a-zA-Z0-9_-]+)|"
    r"why\s+(?:is|does)\s+operation\s+([a-zA-Z0-9_-]+)|"
    r"what\s+is\s+operation\s+([a-zA-Z0-9_-]+)|"
    r"tell\s+me\s+about\s+op(?:eration)?\s+([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)

_IMPACT_KEYWORDS = [
    "what if", "what would happen", "impact of", "simulate",
    "hypothetical", "would it", "if we", "if i",
]

_COST_KEYWORDS = ["cost breakdown", "cost estimate", "detailed cost", "cost analysis"]
_TIME_KEYWORDS = ["time breakdown", "time estimate", "detailed time", "time analysis"]
_SPATIAL_KEYWORDS = ["spatial map", "operation map", "3d map", "where are", "spatial"]
_PACKET_KEYWORDS = ["manufacturing packet", "machining packet", "build packet"]
_RFQ_KEYWORDS = ["rfq", "request for quote", "quote packet", "vendor packet"]
_PDF_KEYWORDS = ["industrial pdf", "full report", "industrial report", "detailed pdf"]


class ConversationalQueryType:
    """Enumeration of Phase C query types."""

    GENERAL = "general"
    EXPLAIN_FEATURE = "explain_feature"
    EXPLAIN_OPERATION = "explain_operation"
    IMPACT = "impact"
    COST_BREAKDOWN = "cost_breakdown"
    TIME_BREAKDOWN = "time_breakdown"
    SPATIAL_MAP = "spatial_map"
    MACHINING_PACKET = "machining_packet"
    RFQ_PACKET = "rfq_packet"
    INDUSTRIAL_PDF = "industrial_pdf"
    CONVERSATION = "conversation"
    MODIFICATION_REDIRECT = "modification_redirect"


def _classify_query(user_message: str) -> tuple[str, dict[str, Any]]:
    """
    Classify a user message into a Phase C query type.

    Returns (query_type, metadata).
    """
    lower = user_message.lower().strip()

    # Explain feature
    m = _EXPLAIN_FEATURE_RE.search(user_message)
    if m:
        fid = next(g for g in m.groups() if g is not None)
        return ConversationalQueryType.EXPLAIN_FEATURE, {"feature_id": fid}

    # Explain operation
    m = _EXPLAIN_OPERATION_RE.search(user_message)
    if m:
        oid = next(g for g in m.groups() if g is not None)
        return ConversationalQueryType.EXPLAIN_OPERATION, {"operation_id": oid}

    # Impact / what-if
    if any(kw in lower for kw in _IMPACT_KEYWORDS):
        return ConversationalQueryType.IMPACT, {}

    # Cost breakdown
    if any(kw in lower for kw in _COST_KEYWORDS):
        return ConversationalQueryType.COST_BREAKDOWN, {}

    # Time breakdown
    if any(kw in lower for kw in _TIME_KEYWORDS):
        return ConversationalQueryType.TIME_BREAKDOWN, {}

    # Spatial map
    if any(kw in lower for kw in _SPATIAL_KEYWORDS):
        return ConversationalQueryType.SPATIAL_MAP, {}

    # Machining packet
    if any(kw in lower for kw in _PACKET_KEYWORDS):
        return ConversationalQueryType.MACHINING_PACKET, {}

    # RFQ
    if any(kw in lower for kw in _RFQ_KEYWORDS):
        return ConversationalQueryType.RFQ_PACKET, {}

    # Industrial PDF
    if any(kw in lower for kw in _PDF_KEYWORDS):
        return ConversationalQueryType.INDUSTRIAL_PDF, {}

    # General deterministic query
    if classify_general_query(user_message) is not None:
        return ConversationalQueryType.GENERAL, {}

    # Fallback: LLM conversational engine
    return ConversationalQueryType.CONVERSATION, {}


# ── Main entry point ──────────────────────────────────────────────────────────

async def handle_conversational_query(
    user_message: str,
    model_id: str,
    session: AsyncSession,
    *,
    plan_id: str | None = None,
    version: int | None = None,
    part_name: str = "",
) -> dict[str, Any]:
    """
    Phase C conversational entry point.

    Routes the user message to the appropriate handler and returns
    a structured response.

    Parameters
    ----------
    user_message : str
        The user's natural-language query.
    model_id : str
        CAD model ID.
    session : AsyncSession
        Active DB session.
    plan_id : str | None
        Specific plan row ID (optional).
    version : int | None
        Specific version (optional, None=latest).
    part_name : str
        Human-readable part name for documents.

    Returns
    -------
    dict
        ``{"type": ..., "data": ..., "message": ...}``
    """

    # ── Build context once ───────────────────────────────────────────────
    ctx = await build_conversation_context(
        model_id, session, version=version, plan_id=plan_id,
    )

    # ── Classify ─────────────────────────────────────────────────────────
    qtype, meta = _classify_query(user_message)
    logger.info(
        "Conversational query: type=%s model=%s msg=%s",
        qtype, model_id, user_message[:80],
    )

    # ── Route ────────────────────────────────────────────────────────────

    if qtype == ConversationalQueryType.GENERAL:
        result = handle_general_query(user_message, ctx)
        return {"type": "general_query", "data": result}

    if qtype == ConversationalQueryType.EXPLAIN_FEATURE:
        fid = meta["feature_id"]
        explanation = await explain_feature(fid, ctx)
        return {
            "type": "feature_explanation",
            "data": explanation.model_dump(),
            "message": explanation.explanation,
        }

    if qtype == ConversationalQueryType.EXPLAIN_OPERATION:
        oid = meta["operation_id"]
        explanation = await explain_operation(oid, ctx)
        return {
            "type": "operation_explanation",
            "data": explanation.model_dump(),
            "message": explanation.explanation,
        }

    if qtype == ConversationalQueryType.IMPACT:
        impact = await simulate_impact(user_message, ctx)
        return {
            "type": "impact_simulation",
            "data": impact.model_dump(),
            "message": impact.summary,
        }

    if qtype == ConversationalQueryType.COST_BREAKDOWN:
        from ai_service.costing.cost_estimator import estimate_manufacturing_cost
        from ai_service.costing.time_simulator import simulate_detailed_time

        time_bd = simulate_detailed_time(ctx)
        cost_bd = estimate_manufacturing_cost(ctx, time_bd)
        return {
            "type": "cost_breakdown",
            "data": cost_bd.model_dump(),
            "message": (
                f"Total estimated cost: ${cost_bd.total_cost:.2f} "
                f"(Machining: ${cost_bd.machining_cost:.2f}, "
                f"Tooling: ${cost_bd.tooling_cost:.2f}, "
                f"Material: ${cost_bd.material_cost:.2f}, "
                f"Setup: ${cost_bd.setup_cost:.2f}, "
                f"Overhead: ${cost_bd.overhead_cost:.2f})"
            ),
        }

    if qtype == ConversationalQueryType.TIME_BREAKDOWN:
        from ai_service.costing.time_simulator import simulate_detailed_time

        time_bd = simulate_detailed_time(ctx)
        return {
            "type": "time_breakdown",
            "data": time_bd.model_dump(),
            "message": (
                f"Total time: {time_bd.total_time:.1f}s "
                f"({time_bd.total_time_minutes:.1f} min). "
                f"Cutting: {time_bd.total_cutting_time:.1f}s, "
                f"Setup: {time_bd.total_setup_time:.1f}s, "
                f"Tool changes: {time_bd.total_tool_change_time:.1f}s. "
                f"Strategy multiplier: {time_bd.strategy_multiplier:.2f}x, "
                f"Complexity multiplier: {time_bd.complexity_multiplier:.2f}x."
            ),
        }

    if qtype == ConversationalQueryType.SPATIAL_MAP:
        from ai_service.visualization.operation_mapper import map_operations_spatial

        spatial = map_operations_spatial(ctx)
        return {
            "type": "spatial_map",
            "data": spatial.model_dump(),
            "message": (
                f"Spatial map generated: {spatial.total_operations} operations "
                f"across {len(ctx.setups)} setup(s)."
            ),
        }

    if qtype == ConversationalQueryType.MACHINING_PACKET:
        from ai_service.documentation.machining_packet_builder import build_machining_packet

        packet = build_machining_packet(ctx, part_name=part_name)
        return {
            "type": "machining_packet",
            "data": packet.model_dump(),
            "message": (
                f"Manufacturing packet built: {packet.feature_count} features, "
                f"{len(packet.operations)} operations, cost ${packet.cost_breakdown.get('total_cost', 0):.2f}."
            ),
        }

    if qtype == ConversationalQueryType.RFQ_PACKET:
        from ai_service.rfq.rfq_packet_builder import build_rfq_packet

        rfq = build_rfq_packet(ctx, part_name=part_name)
        return {
            "type": "rfq_packet",
            "data": rfq.model_dump(),
            "message": (
                f"RFQ packet generated: {rfq.complexity_class} complexity, "
                f"est. lead time {rfq.estimated_lead_time_days} days, "
                f"est. cost ${rfq.estimated_total_cost or 0:.2f}."
            ),
        }

    if qtype == ConversationalQueryType.INDUSTRIAL_PDF:
        # Return a signal that the route should generate a PDF binary
        return {
            "type": "industrial_pdf_request",
            "data": {"model_id": model_id, "plan_id": ctx.plan_id, "version": ctx.version},
            "message": "Industrial PDF report ready for generation.",
        }

    # ── Default: conversational engine ───────────────────────────────────
    answer = await conversational_engine_answer(user_message, ctx)

    if answer.is_modification_request:
        return {
            "type": "modification_redirect",
            "data": {"original_message": user_message},
            "message": (
                "This looks like a plan modification request. "
                "Routing to the refinement engine..."
            ),
        }

    return {
        "type": "conversation",
        "data": {
            "answer": answer.answer,
            "referenced_feature_ids": answer.referenced_feature_ids,
            "referenced_operation_ids": answer.referenced_operation_ids,
            "confidence": answer.confidence,
        },
        "message": answer.answer,
    }
