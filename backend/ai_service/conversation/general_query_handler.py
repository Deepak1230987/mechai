"""
General Query Handler — deterministic answers for structured queries.

Answers questions that do NOT require LLM by extracting data directly
from ConversationContext.  Returns structured JSON.

Examples:
  • "How many features?"  → { "feature_count": 5 }
  • "What is the stock size?" → { "stock_dimensions": {...} }
  • "List all tools"  → { "tools": [...] }
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ai_service.conversation.context_builder import ConversationContext

logger = logging.getLogger("ai_service.conversation.general_query_handler")


# ── Query classifiers (keyword-based, no LLM) ────────────────────────────────

_QUERIES: list[tuple[list[str], str]] = [
    (["feature count", "how many features", "number of features"], "feature_count"),
    (["hole count", "how many holes", "number of holes"], "hole_count"),
    (["stock dimension", "stock size", "raw material size"], "stock_dimensions"),
    (["complexity", "complexity score", "complexity level"], "complexity"),
    (["total time", "estimated time", "machining time", "how long"], "total_time"),
    (["total cost", "estimated cost", "how much"], "total_cost"),
    (["tool list", "list tools", "what tools", "which tools"], "tool_list"),
    (["setup count", "how many setups", "number of setups"], "setup_count"),
    (["operation count", "how many operations", "number of operations"], "operation_count"),
    (["material", "what material", "workpiece material"], "material"),
    (["machine type", "what machine", "which machine"], "machine_type"),
    (["version", "plan version", "current version"], "version"),
    (["strategy", "selected strategy", "current strategy"], "strategy"),
    (["risk", "warnings", "risk flags", "manufacturability"], "risks"),
    (["datum", "datum face", "work coordinate"], "datum"),
]


def classify_general_query(user_message: str) -> str | None:
    """
    Return a query type key if the message matches a known general query.

    Returns None if no deterministic handler applies.
    """
    lower = user_message.lower().strip()
    for keywords, qtype in _QUERIES:
        for kw in keywords:
            if kw in lower:
                return qtype
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def handle_general_query(
    user_message: str,
    ctx: ConversationContext,
) -> dict[str, Any] | None:
    """
    Handle a deterministic general query.

    Returns structured JSON dict, or None if the query is not general.
    """
    qtype = classify_general_query(user_message)
    if qtype is None:
        return None

    handler = _HANDLERS.get(qtype)
    if handler is None:
        return None

    logger.debug("General query: type=%s message=%s", qtype, user_message[:80])
    return handler(ctx)


# ── Handler implementations ──────────────────────────────────────────────────

def _feature_count(ctx: ConversationContext) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    for f in ctx.features:
        ftype = f.get("type", "UNKNOWN")
        by_type[ftype] = by_type.get(ftype, 0) + 1
    return {
        "query": "feature_count",
        "feature_count": len(ctx.features),
        "by_type": by_type,
    }


def _hole_count(ctx: ConversationContext) -> dict[str, Any]:
    holes = [f for f in ctx.features if f.get("type", "").upper() in ("HOLE", "THROUGH_HOLE", "BLIND_HOLE", "COUNTERBORE")]
    subtypes: dict[str, int] = {}
    for h in holes:
        st = h.get("hole_subtype", h.get("type", "HOLE"))
        subtypes[st] = subtypes.get(st, 0) + 1
    return {
        "query": "hole_count",
        "hole_count": len(holes),
        "subtypes": subtypes,
        "hole_ids": [h.get("id", h.get("feature_id", "?")) for h in holes],
    }


def _stock_dimensions(ctx: ConversationContext) -> dict[str, Any]:
    return {
        "query": "stock_dimensions",
        "stock_recommendation": ctx.stock_recommendation,
    }


def _complexity(ctx: ConversationContext) -> dict[str, Any]:
    return {
        "query": "complexity",
        "complexity_score": ctx.complexity_score,
        "complexity_level": ctx.complexity_level,
    }


def _total_time(ctx: ConversationContext) -> dict[str, Any]:
    op_breakdown: dict[str, float] = {}
    for op in ctx.operations:
        op_breakdown[op.id] = op.estimated_time
    return {
        "query": "total_time",
        "total_time": ctx.cost_time.total_time,
        "operation_breakdown": op_breakdown,
    }


def _total_cost(ctx: ConversationContext) -> dict[str, Any]:
    return {
        "query": "total_cost",
        "total_cost": ctx.cost_time.total_cost,
        "note": "Cost is computed from time simulation + machine rate" if ctx.cost_time.total_cost else "Cost not yet computed",
    }


def _tool_list(ctx: ConversationContext) -> dict[str, Any]:
    tools = [
        {
            "id": t.id,
            "type": t.type,
            "diameter": t.diameter,
            "max_depth": t.max_depth,
            "rpm_range": [t.recommended_rpm_min, t.recommended_rpm_max],
        }
        for t in ctx.tools
    ]
    return {"query": "tool_list", "tools": tools, "tool_count": len(tools)}


def _setup_count(ctx: ConversationContext) -> dict[str, Any]:
    setups = [
        {
            "setup_id": s.setup_id,
            "orientation": s.orientation,
            "datum_face_id": s.datum_face_id,
            "operation_count": len(s.operations),
        }
        for s in ctx.setups
    ]
    return {"query": "setup_count", "setup_count": len(setups), "setups": setups}


def _operation_count(ctx: ConversationContext) -> dict[str, Any]:
    return {
        "query": "operation_count",
        "operation_count": len(ctx.operations),
        "operations": [
            {"id": op.id, "type": op.type, "feature_id": op.feature_id}
            for op in ctx.operations
        ],
    }


def _material(ctx: ConversationContext) -> dict[str, Any]:
    return {"query": "material", "material": ctx.material}


def _machine_type(ctx: ConversationContext) -> dict[str, Any]:
    return {"query": "machine_type", "machine_type": ctx.machine_type}


def _version(ctx: ConversationContext) -> dict[str, Any]:
    return {
        "query": "version",
        "version": ctx.version,
        "plan_id": ctx.plan_id,
        "approval_status": ctx.approval_status,
        "is_rollback": ctx.is_rollback,
    }


def _strategy(ctx: ConversationContext) -> dict[str, Any]:
    return {
        "query": "strategy",
        "selected_strategy": ctx.selected_strategy,
        "available_strategies": [
            {"name": s.name, "description": s.description, "estimated_time": s.estimated_time}
            for s in ctx.strategies
        ],
    }


def _risks(ctx: ConversationContext) -> dict[str, Any]:
    return {
        "query": "risks",
        "risk_count": len(ctx.risks),
        "risks": [
            {
                "code": r.code,
                "severity": r.severity,
                "message": r.message,
                "affected_operations": r.affected_operation_ids,
                "mitigation": r.mitigation,
            }
            for r in ctx.risks
        ],
        "manufacturability_flags": ctx.manufacturability_flags,
    }


def _datum(ctx: ConversationContext) -> dict[str, Any]:
    return {
        "query": "datum",
        "datum_candidates": ctx.datum_candidates,
        "setup_datums": [
            {"setup_id": s.setup_id, "datum_face_id": s.datum_face_id}
            for s in ctx.setups
        ],
    }


_HANDLERS: dict[str, Any] = {
    "feature_count": _feature_count,
    "hole_count": _hole_count,
    "stock_dimensions": _stock_dimensions,
    "complexity": _complexity,
    "total_time": _total_time,
    "total_cost": _total_cost,
    "tool_list": _tool_list,
    "setup_count": _setup_count,
    "operation_count": _operation_count,
    "material": _material,
    "machine_type": _machine_type,
    "version": _version,
    "strategy": _strategy,
    "risks": _risks,
    "datum": _datum,
}
