"""
Narrative Builder — generates comprehensive initial workspace narrative.

Produces a detailed structured narrative covering:
  • Part overview (material, geometry, complexity)
  • Setup explanation (orientations, datum reasoning)
  • Operation sequence (step-by-step with tool + feature references)
  • Tool selection rationale
  • Strategy comparison
  • Risk assessment
  • Cost & time reasoning

This is purely deterministic — no LLM required.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_service.conversation.context_builder import ConversationContext

logger = logging.getLogger("ai_service.conversation.narrative_builder")


def build_initial_narrative(ctx: ConversationContext) -> dict[str, Any]:
    """
    Build a comprehensive initial narrative for the workspace.

    Returns a dict with structured sections and a full_text markdown string.
    """
    sections: list[dict[str, str]] = []

    # ── 1. Part Overview ─────────────────────────────────────────────────
    geo = ctx.geometry_summary
    bbox = geo.get("bounding_box", {})
    length = bbox.get("length", bbox.get("dx", 0))
    width = bbox.get("width", bbox.get("dy", 0))
    height = bbox.get("height", bbox.get("dz", 0))
    volume = geo.get("volume", 0)
    surface_area = geo.get("surface_area", 0)

    material_display = ctx.material.replace("_", " ").title() if ctx.material else "Unknown"

    overview_text = (
        f"This is a **{material_display}** part with dimensions "
        f"**{length:.1f} × {width:.1f} × {height:.1f} mm** "
        f"(Volume: {volume:.0f} mm³, Surface area: {surface_area:.0f} mm²). "
        f"The complexity score is **{ctx.complexity_score:.1f}/10** "
        f"({ctx.complexity_level}), indicating "
    )
    if ctx.complexity_score < 3:
        overview_text += "a straightforward part suitable for basic 3-axis machining."
    elif ctx.complexity_score < 6:
        overview_text += "moderate manufacturing complexity requiring careful setup planning."
    else:
        overview_text += "high complexity requiring advanced fixturing and tool selection."

    sections.append({
        "title": "Part Overview",
        "icon": "cube",
        "content": overview_text,
    })

    # ── 2. Setup Explanation ─────────────────────────────────────────────
    if ctx.setups:
        setup_lines = []
        for i, setup in enumerate(ctx.setups, 1):
            op_count = len(setup.operations)
            datum_ref = f" (datum: {setup.datum_face_id})" if setup.datum_face_id else ""
            setup_lines.append(
                f"**Setup {i} — {setup.orientation}**{datum_ref}: "
                f"{op_count} operation{'s' if op_count != 1 else ''}"
            )

        if len(ctx.setups) == 1:
            setup_intro = (
                f"The plan requires **1 setup** in the **{ctx.setups[0].orientation}** "
                f"orientation. All {len(ctx.operations)} operations can be completed "
                f"without re-fixturing, which minimizes setup time and registration error."
            )
        else:
            setup_intro = (
                f"The plan requires **{len(ctx.setups)} setups** to access "
                f"all machining features. Each setup flips the part to a "
                f"different orientation:"
            )

        setup_text = setup_intro + "\n\n" + "\n".join(f"- {line}" for line in setup_lines)
        sections.append({
            "title": "Setup Strategy",
            "icon": "layers",
            "content": setup_text,
        })

    # ── 3. Operation Sequence ────────────────────────────────────────────
    if ctx.operations:
        op_lines = []
        tool_map = {t.id: t for t in ctx.tools}

        for i, op in enumerate(ctx.operations, 1):
            tool = tool_map.get(op.tool_id)
            tool_desc = (
                f"{tool.type.replace('_', ' ')} Ø{tool.diameter}mm"
                if tool else op.tool_id
            )
            feature_ref = op.feature_id

            op_desc = _describe_operation(op.type)
            op_lines.append(
                f"**Step {i}: {op.type.replace('_', ' ')}** — "
                f"{op_desc} on feature `{feature_ref}` "
                f"using {tool_desc} "
                f"(est. {op.estimated_time:.1f}s)"
            )

        op_text = (
            f"The machining sequence consists of **{len(ctx.operations)} operations** "
            f"planned in optimal order to minimize tool changes and "
            f"maintain dimensional accuracy:\n\n"
            + "\n".join(f"{i}. {line}" for i, line in enumerate(op_lines, 1))
        )
        sections.append({
            "title": "Operation Sequence",
            "icon": "list-ordered",
            "content": op_text,
        })

    # ── 4. Tool Selection ────────────────────────────────────────────────
    if ctx.tools:
        tool_lines = []
        for tool in ctx.tools:
            # Count how many operations use this tool
            ops_using = [op for op in ctx.operations if op.tool_id == tool.id]
            tool_desc = _describe_tool_selection(tool, ops_using, ctx.material)
            tool_lines.append(
                f"**{tool.id}** — {tool.type.replace('_', ' ')} Ø{tool.diameter}mm: "
                f"{tool_desc}"
            )

        tool_text = (
            f"**{len(ctx.tools)} cutting tools** selected for this plan:\n\n"
            + "\n".join(f"- {line}" for line in tool_lines)
        )
        sections.append({
            "title": "Tool Selection",
            "icon": "wrench",
            "content": tool_text,
        })

    # ── 5. Strategy Comparison ───────────────────────────────────────────
    if ctx.strategies:
        strat_lines = []
        for strat in ctx.strategies:
            is_active = strat.name == ctx.selected_strategy
            marker = " ← **active**" if is_active else ""
            strat_lines.append(
                f"**{strat.name}**: {strat.description or 'Standard parameters'} "
                f"(est. {strat.estimated_time:.0f}s){marker}"
            )

        strat_text = (
            f"Currently using the **{ctx.selected_strategy}** strategy. "
            f"Available strategies:\n\n"
            + "\n".join(f"- {line}" for line in strat_lines)
            + "\n\nYou can switch strategies in the Strategy panel to see "
            "updated cost and time estimates."
        )
        sections.append({
            "title": "Strategy Comparison",
            "icon": "zap",
            "content": strat_text,
        })

    # ── 6. Risk Assessment ───────────────────────────────────────────────
    if ctx.risks:
        risk_lines = []
        for risk in ctx.risks:
            ops = ", ".join(risk.affected_operation_ids) if risk.affected_operation_ids else "general"
            risk_lines.append(
                f"**[{risk.severity}] {risk.code}**: {risk.message} "
                f"(affects: {ops})"
            )
            if risk.mitigation:
                risk_lines.append(f"  → Mitigation: {risk.mitigation}")

        risk_text = (
            f"**{len(ctx.risks)} risk(s)** identified:\n\n"
            + "\n".join(f"- {line}" for line in risk_lines)
        )
    else:
        risk_text = (
            "No significant manufacturing risks identified for this plan. "
            "The part geometry and selected parameters are within standard "
            "machining capabilities."
        )
    sections.append({
        "title": "Risk Assessment",
        "icon": "alert-triangle",
        "content": risk_text,
    })

    # ── 7. Cost & Time ───────────────────────────────────────────────────
    ct = ctx.cost_time
    cost_text = (
        f"**Estimated machining time: {ct.total_time:.1f}s "
        f"({ct.total_time / 60:.1f} minutes)** across "
        f"{ct.operation_count} operations using {ct.tool_count} tools "
        f"in {ct.setup_count} setup(s)."
    )
    if ct.total_cost is not None:
        cost_text += f"\n\n**Estimated total cost: ${ct.total_cost:.2f}**"
    cost_text += (
        "\n\nUse the Cost panel for detailed breakdown. "
        "Ask me about specific operations or features for "
        "more detailed estimates."
    )
    sections.append({
        "title": "Cost & Time Summary",
        "icon": "dollar-sign",
        "content": cost_text,
    })

    # ── Build full_text ──────────────────────────────────────────────────
    full_lines = [
        f"## Manufacturing Plan Analysis — v{ctx.version}\n",
    ]
    for section in sections:
        full_lines.append(f"### {section['title']}\n")
        full_lines.append(section["content"])
        full_lines.append("")

    full_lines.append(
        "---\n"
        "*Ask me anything about this plan — tool choices, "
        "setup reasoning, cost optimization, or risk mitigation. "
        "You can also request plan modifications.*"
    )

    return {
        "sections": sections,
        "full_text": "\n".join(full_lines),
        "model_id": ctx.model_id,
        "plan_id": ctx.plan_id,
        "version": ctx.version,
        "strategy": ctx.selected_strategy,
    }


def _describe_operation(op_type: str) -> str:
    """Human-readable description for an operation type."""
    descriptions = {
        "FACE_MILLING": "Facing pass to establish reference surface and stock removal",
        "POCKET_ROUGHING": "Rough pocket machining for bulk material removal",
        "POCKET_FINISHING": "Finish pass for final pocket dimensions and surface quality",
        "SLOT_MILLING": "Slot machining for through or blind slot features",
        "DRILLING": "Hole drilling operation",
        "ROUGH_TURNING": "Rough turning for cylindrical stock removal",
        "FINISH_TURNING": "Finish turning for final diameter and surface finish",
        "FINISH_CONTOUR": "Finish contour pass along the part profile edge",
    }
    return descriptions.get(op_type, f"Machining operation ({op_type})")


def _describe_tool_selection(tool, ops_using, material: str) -> str:
    """Explain why a tool was selected."""
    op_types = list(set(op.type for op in ops_using))
    op_desc = ", ".join(t.replace("_", " ").lower() for t in op_types)

    material_note = ""
    if "ALUMINUM" in material.upper():
        material_note = " — high helix angle recommended for aluminum chip evacuation"
    elif "STEEL" in material.upper():
        material_note = " — coated carbide recommended for steel hardness"
    elif "TITANIUM" in material.upper():
        material_note = " — low speed, high feed recommended for titanium heat management"

    return (
        f"Used for {op_desc} "
        f"({len(ops_using)} operation{'s' if len(ops_using) != 1 else ''})"
        f"{material_note}"
    )
