"""
General Query Handler — deterministic answers for structured queries.

Answers questions that do NOT require LLM by extracting data directly
from ConversationContext.  Returns structured JSON with a natural-language
``message`` field for display.

Examples:
  • "How many features?"  → { "feature_count": 5, "message": "..." }
  • "What is the stock size?" → { "stock_dimensions": {...}, "message": "..." }
  • "List all tools"  → { "tools": [...], "message": "..." }
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

    Returns structured JSON dict with ``data`` and ``message`` keys,
    or None if the query is not general.
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

    if not ctx.features:
        msg = (
            "**No geometric features** were detected in this part's intelligence report. "
            "The plan uses synthetic features derived from the bounding box dimensions. "
            "This is typical for simple prismatic parts or when the STEP file "
            "has limited feature-level detail."
        )
    else:
        type_lines = "\n".join(f"- **{t}**: {c}" for t, c in by_type.items())
        msg = (
            f"**{len(ctx.features)} feature(s)** detected:\n\n{type_lines}"
        )

    return {
        "query": "feature_count",
        "feature_count": len(ctx.features),
        "by_type": by_type,
        "message": msg,
    }


def _hole_count(ctx: ConversationContext) -> dict[str, Any]:
    holes = [
        f for f in ctx.features
        if f.get("type", "").upper() in ("HOLE", "THROUGH_HOLE", "BLIND_HOLE", "COUNTERBORE")
    ]
    subtypes: dict[str, int] = {}
    for h in holes:
        st = h.get("hole_subtype", h.get("type", "HOLE"))
        subtypes[st] = subtypes.get(st, 0) + 1

    if not holes:
        if not ctx.features:
            msg = (
                "**No holes detected.** The intelligence report contains no geometric "
                "features — this part appears to be a simple prismatic shape without "
                "hole features. If you need drilling operations, you can request "
                "modifications in the chat."
            )
        else:
            feature_types = set(f.get("type", "UNKNOWN") for f in ctx.features)
            msg = (
                f"**No hole features** in this part. The detected feature types are: "
                f"{', '.join(f'**{t}**' for t in sorted(feature_types))}. "
                f"No drilling operations are planned."
            )
    else:
        hole_lines = "\n".join(
            f"- `{h.get('id', h.get('feature_id', '?'))}` ({h.get('type', 'HOLE')})"
            for h in holes
        )
        msg = f"**{len(holes)} hole(s)** detected:\n\n{hole_lines}"
        if subtypes:
            sub_desc = ", ".join(f"{k}: {v}" for k, v in subtypes.items())
            msg += f"\n\nSubtypes: {sub_desc}"

    return {
        "query": "hole_count",
        "hole_count": len(holes),
        "subtypes": subtypes,
        "hole_ids": [h.get("id", h.get("feature_id", "?")) for h in holes],
        "message": msg,
    }


def _stock_dimensions(ctx: ConversationContext) -> dict[str, Any]:
    stock = ctx.stock_recommendation
    if stock and isinstance(stock, dict):
        dims = stock.get("dimensions", stock)
        msg = (
            f"**Stock recommendation:**\n\n"
            f"- Dimensions: {dims}\n"
            f"- This accommodates the part bounding box plus standard machining allowance."
        )
    else:
        bbox = ctx.geometry_summary.get("bounding_box", {})
        length = bbox.get("length", bbox.get("dx", 0))
        width = bbox.get("width", bbox.get("dy", 0))
        height = bbox.get("height", bbox.get("dz", 0))
        msg = (
            f"No explicit stock recommendation available. "
            f"Part bounding box is **{length:.1f} × {width:.1f} × {height:.1f} mm**. "
            f"Standard practice: add 2-5mm per side for stock allowance."
        )
    return {
        "query": "stock_dimensions",
        "stock_recommendation": ctx.stock_recommendation,
        "message": msg,
    }


def _complexity(ctx: ConversationContext) -> dict[str, Any]:
    level_desc = {
        "LOW": "straightforward part suitable for basic 3-axis machining",
        "MEDIUM": "moderate complexity requiring careful tool and setup planning",
        "HIGH": "high complexity requiring advanced fixturing and possibly multi-axis",
        "VERY_HIGH": "very high complexity — critical review of tool paths and tolerances recommended",
    }
    desc = level_desc.get(ctx.complexity_level, "standard complexity")
    msg = (
        f"**Complexity: {ctx.complexity_score:.1f}/10 ({ctx.complexity_level})**\n\n"
        f"This indicates {desc}. "
        f"Score factors: feature count ({len(ctx.features)}), "
        f"depth ratios, multi-axis needs, and setup count ({len(ctx.setups)})."
    )
    return {
        "query": "complexity",
        "complexity_score": ctx.complexity_score,
        "complexity_level": ctx.complexity_level,
        "message": msg,
    }


def _total_time(ctx: ConversationContext) -> dict[str, Any]:
    op_breakdown: dict[str, float] = {}
    for op in ctx.operations:
        op_breakdown[op.id] = op.estimated_time

    op_lines = "\n".join(
        f"- `{op.id}` ({op.type}): **{op.estimated_time:.1f}s** on `{op.feature_id}`"
        for op in ctx.operations
    )
    msg = (
        f"**Total estimated machining time: {ctx.cost_time.total_time:.1f}s "
        f"({ctx.cost_time.total_time / 60:.1f} min)**\n\n"
        f"Across {ctx.cost_time.operation_count} operations "
        f"in {ctx.cost_time.setup_count} setup(s) "
        f"using {ctx.cost_time.tool_count} tool(s).\n"
    )
    if op_lines:
        msg += f"\n**Per-operation breakdown:**\n{op_lines}"
    msg += f"\n\nStrategy: **{ctx.selected_strategy}**"

    return {
        "query": "total_time",
        "total_time": ctx.cost_time.total_time,
        "operation_breakdown": op_breakdown,
        "message": msg,
    }


def _total_cost(ctx: ConversationContext) -> dict[str, Any]:
    cost = ctx.cost_time.total_cost
    if cost is not None:
        msg = (
            f"**Estimated total cost: ${cost:.2f}**\n\n"
            f"Based on {ctx.cost_time.total_time:.1f}s machining time, "
            f"{ctx.cost_time.tool_count} tool(s) and "
            f"{ctx.cost_time.setup_count} setup(s). "
            f"See the Cost panel for detailed breakdown by category."
        )
    else:
        msg = (
            f"Cost estimate has not been computed yet. "
            f"Machining time is **{ctx.cost_time.total_time:.1f}s** "
            f"with {ctx.cost_time.operation_count} operations. "
            f"Check the Cost panel once it loads."
        )
    return {
        "query": "total_cost",
        "total_cost": ctx.cost_time.total_cost,
        "message": msg,
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

    tool_lines = []
    for t in ctx.tools:
        ops_using = [op for op in ctx.operations if op.tool_id == t.id]
        op_desc = ", ".join(set(op.type.replace("_", " ") for op in ops_using))
        tool_lines.append(
            f"- **`{t.id}`** — {t.type.replace('_', ' ')} Ø{t.diameter}mm "
            f"(RPM: {t.recommended_rpm_min}–{t.recommended_rpm_max})\n"
            f"  Used for: {op_desc or 'N/A'} "
            f"({len(ops_using)} op{'s' if len(ops_using) != 1 else ''})"
        )

    msg = f"**{len(tools)} tool(s)** in the current plan:\n\n" + "\n".join(tool_lines)

    if "ALUMINUM" in ctx.material.upper():
        msg += (
            "\n\n*For aluminum: high-helix geometry and sharp edges "
            "recommended for efficient chip evacuation.*"
        )

    return {"query": "tool_list", "tools": tools, "tool_count": len(tools), "message": msg}


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

    setup_lines = []
    for s in ctx.setups:
        op_count = len(s.operations)
        setup_lines.append(
            f"- **{s.setup_id}** — {s.orientation} "
            f"(datum: `{s.datum_face_id}`), "
            f"{op_count} operation{'s' if op_count != 1 else ''}"
        )

    if len(ctx.setups) == 1:
        intro = (
            f"**1 setup** in the **{ctx.setups[0].orientation}** orientation. "
            f"All operations complete without re-fixturing — minimal setup time "
            f"and maximum positional accuracy."
        )
    else:
        intro = (
            f"**{len(ctx.setups)} setups** required to access all features:"
        )

    msg = intro + "\n\n" + "\n".join(setup_lines)

    return {"query": "setup_count", "setup_count": len(setups), "setups": setups, "message": msg}


def _operation_count(ctx: ConversationContext) -> dict[str, Any]:
    op_lines = []
    tool_map = {t.id: t for t in ctx.tools}
    for i, op in enumerate(ctx.operations, 1):
        tool = tool_map.get(op.tool_id)
        tool_desc = (
            f"{tool.type.replace('_', ' ')} Ø{tool.diameter}mm"
            if tool else op.tool_id
        )
        op_lines.append(
            f"{i}. **{op.type.replace('_', ' ')}** (`{op.id}`)\n"
            f"   Feature: `{op.feature_id}` | Tool: {tool_desc} | "
            f"Time: {op.estimated_time:.1f}s"
        )

    msg = (
        f"**{len(ctx.operations)} operation(s)** planned:\n\n"
        + "\n".join(op_lines)
        + f"\n\n**Total time: {ctx.cost_time.total_time:.1f}s** "
        f"({ctx.selected_strategy} strategy)"
    )

    return {
        "query": "operation_count",
        "operation_count": len(ctx.operations),
        "operations": [
            {"id": op.id, "type": op.type, "feature_id": op.feature_id}
            for op in ctx.operations
        ],
        "message": msg,
    }


def _material(ctx: ConversationContext) -> dict[str, Any]:
    material_display = ctx.material.replace("_", " ").title()
    msg = (
        f"**Material: {material_display}**\n\n"
        f"Machine type: **{ctx.machine_type.replace('_', ' ')}**. "
        f"Material properties determine feed rates, spindle speeds, "
        f"tool coatings, and coolant strategy."
    )
    return {"query": "material", "material": ctx.material, "message": msg}


def _machine_type(ctx: ConversationContext) -> dict[str, Any]:
    msg = (
        f"**Machine: {ctx.machine_type.replace('_', ' ')}**\n\n"
        f"Material: **{ctx.material.replace('_', ' ').title()}**, "
        f"Complexity: {ctx.complexity_score:.1f}/10."
    )
    return {"query": "machine_type", "machine_type": ctx.machine_type, "message": msg}


def _version(ctx: ConversationContext) -> dict[str, Any]:
    msg = (
        f"**Plan version {ctx.version}** "
        f"(ID: `{ctx.plan_id or 'N/A'}`)\n\n"
        f"- Approval status: **{ctx.approval_status}**\n"
        f"- Is rollback: {'Yes' if ctx.is_rollback else 'No'}"
    )
    return {
        "query": "version",
        "version": ctx.version,
        "plan_id": ctx.plan_id,
        "approval_status": ctx.approval_status,
        "is_rollback": ctx.is_rollback,
        "message": msg,
    }


def _strategy(ctx: ConversationContext) -> dict[str, Any]:
    strat_lines = []
    for s in ctx.strategies:
        marker = " ← **active**" if s.name == ctx.selected_strategy else ""
        strat_lines.append(
            f"- **{s.name}**: {s.description or 'Standard parameters'} "
            f"(~{s.estimated_time:.0f}s){marker}"
        )

    msg = (
        f"Currently using **{ctx.selected_strategy}** strategy.\n\n"
        + ("\n".join(strat_lines) if strat_lines else "No alternative strategies available.")
        + "\n\nSwitch strategies in the Strategy panel for live cost/time comparison."
    )

    return {
        "query": "strategy",
        "selected_strategy": ctx.selected_strategy,
        "available_strategies": [
            {"name": s.name, "description": s.description, "estimated_time": s.estimated_time}
            for s in ctx.strategies
        ],
        "message": msg,
    }


def _risks(ctx: ConversationContext) -> dict[str, Any]:
    if not ctx.risks:
        msg = (
            "**No manufacturing risks** flagged for this plan. "
            "The geometry and parameters are within standard machining capabilities "
            f"for **{ctx.machine_type.replace('_', ' ')}** with "
            f"**{ctx.material.replace('_', ' ').title()}**."
        )
    else:
        risk_lines = []
        for r in ctx.risks:
            ops = ", ".join(f"`{o}`" for o in r.affected_operation_ids) if r.affected_operation_ids else "general"
            risk_lines.append(
                f"- **[{r.severity}] {r.code}**: {r.message} (affects: {ops})"
            )
            if r.mitigation:
                risk_lines.append(f"  → *Mitigation:* {r.mitigation}")
        msg = f"**{len(ctx.risks)} risk(s)** identified:\n\n" + "\n".join(risk_lines)

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
        "message": msg,
    }


def _datum(ctx: ConversationContext) -> dict[str, Any]:
    if ctx.datum_candidates:
        datum_lines = []
        for dc in ctx.datum_candidates:
            if isinstance(dc, dict):
                datum_lines.append(
                    f"- Face `{dc.get('face_id', '?')}`: "
                    f"area={dc.get('area', '?')}, "
                    f"flatness={dc.get('flatness_score', '?')}"
                )
        msg = "**Datum candidates:**\n\n" + "\n".join(datum_lines)
    else:
        msg = "No datum candidates identified in the intelligence report."

    setup_datums = [
        {"setup_id": s.setup_id, "datum_face_id": s.datum_face_id}
        for s in ctx.setups
    ]
    if setup_datums:
        msg += "\n\n**Setup datum assignments:**\n"
        for sd in setup_datums:
            msg += f"- {sd['setup_id']}: datum `{sd['datum_face_id']}`\n"

    return {
        "query": "datum",
        "datum_candidates": ctx.datum_candidates,
        "setup_datums": setup_datums,
        "message": msg,
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
