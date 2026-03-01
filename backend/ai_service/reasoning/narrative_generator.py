"""
Narrative Generator — LLM-powered explanation of the machining plan.

Explains:
  - Setup decisions (why features grouped this way, datum logic)
  - Tool logic (why each tool was selected)
  - Risk mitigation (how warnings are addressed)
  - Why optimization improves the plan
  - References feature IDs and datum faces

Falls back to deterministic template if LLM is unavailable.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from ai_service.schemas.machining_plan import MachiningPlanResponse
from ai_service.schemas.planning_context import PlanningContext
from ai_service.services.langchain_pipeline import _build_llm

logger = logging.getLogger("ai_service.reasoning.narrative_generator")


_NARRATIVE_SYSTEM = """\
You are a senior manufacturing engineer writing a Process Planning Sheet.

Write a professional, structured manufacturing narrative for CNC machining.
REQUIRED SECTIONS:
1. **Raw Material Selection** — material grade, form (bar / plate / billet)
2. **Blank Size Recommendation** — minimum stock dimensions with allowances
3. **Workholding Method** — vise, chuck, fixture recommendation with reasoning
4. **Setup Instructions** — orientation, datum references ({datum}), alignment notes
5. **Operation Sequence** — step-by-step referencing feature IDs and tool IDs
6. **Tool Selection Rationale** — why each tool was chosen
7. **Risk Mitigation** — how each manufacturing risk is addressed
8. **Optimization Summary** — what the AI optimizer changed and why
9. **Safety Notes** — chip evacuation, coolant, clamping checks
10. **Post-Processing** — deburring, surface finish, inspection points

REFERENCES:
- Feature IDs: {feature_ids}
- Datum face: {datum}
- Complexity: {complexity}

Use metric units (mm, mm/min, RPM).
Do NOT use markdown code blocks — use ## section headers.
"""

_NARRATIVE_USER = """\
Material: {material}
Machine type: {machine_type}
Volume: {volume} mm³
Surface area: {surface_area} mm²

Plan ({num_ops} operations, {num_setups} setups, {num_tools} tools):
{plan_json}

Risks:
{risks_json}

Strategies available:
{strategies_json}

Generate the complete manufacturing narrative.
"""


async def generate_narrative(
    plan: MachiningPlanResponse,
    context: PlanningContext,
) -> str:
    """
    Generate a manufacturing process narrative for the plan.

    Returns:
        Markdown-formatted narrative text.
    """
    llm = _build_llm()

    if llm is not None:
        try:
            return await _generate_with_llm(llm, plan, context)
        except Exception:
            logger.exception("LLM narrative generation failed — using template")

    return _generate_template(plan, context)


async def _generate_with_llm(
    llm: Any,
    plan: MachiningPlanResponse,
    context: PlanningContext,
) -> str:
    """LLM-powered narrative generation."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", _NARRATIVE_SYSTEM),
        ("human", _NARRATIVE_USER),
    ])
    chain = prompt | llm | StrOutputParser()

    feature_ids = ", ".join(f.id for f in context.features)
    plan_dict = plan.model_dump(exclude={"plan_id"})
    risks_json = json.dumps(
        [r.model_dump() for r in plan.risks], indent=2, default=str
    )
    strategies_json = json.dumps(
        [s.model_dump() for s in plan.strategies], indent=2, default=str
    )

    result = await chain.ainvoke({
        "datum": context.datum_primary or "N/A",
        "feature_ids": feature_ids,
        "complexity": context.complexity_score,
        "material": context.material,
        "machine_type": context.machine_type,
        "volume": context.geometry.volume,
        "surface_area": context.geometry.surface_area,
        "num_ops": len(plan.operations),
        "num_setups": len(plan.setups),
        "num_tools": len(plan.tools),
        "plan_json": json.dumps(plan_dict, indent=2, default=str),
        "risks_json": risks_json,
        "strategies_json": strategies_json,
    })

    logger.info("Narrative generated via LLM: %d chars", len(result))
    return result


def _generate_template(
    plan: MachiningPlanResponse,
    context: PlanningContext,
) -> str:
    """Deterministic template-based narrative fallback."""
    lines = [
        f"## Manufacturing Process Narrative",
        f"",
        f"**Material:** {context.material}",
        f"**Machine:** {context.machine_type}",
        f"**Complexity:** {context.complexity_score:.2f}",
        f"**Primary Datum:** {context.datum_primary or 'N/A'}",
        f"",
        f"## Setup Summary",
    ]

    for setup in plan.setups:
        lines.append(
            f"- **{setup.setup_id[:8]}** — Orientation: {setup.orientation}, "
            f"Operations: {len(setup.operations)}"
        )

    lines.extend(["", "## Operation Sequence", ""])

    for i, op in enumerate(plan.operations, 1):
        lines.append(
            f"{i}. **{op.type}** (Feature: {op.feature_id[:8]}) — "
            f"Tool: {op.tool_id}, Time: {op.estimated_time:.1f}s"
        )

    if plan.risks:
        lines.extend(["", "## Risk Warnings", ""])
        for risk in plan.risks:
            lines.append(
                f"- **{risk.code}** [{risk.severity}]: {risk.message}"
            )
            if risk.mitigation:
                lines.append(f"  Mitigation: {risk.mitigation}")

    lines.extend([
        "",
        f"## Total Estimated Time: {plan.estimated_time:.1f}s",
        f"## Strategy: {plan.selected_strategy}",
    ])

    if plan.llm_justification:
        lines.extend(["", "## AI Optimization Notes", "", plan.llm_justification])

    return "\n".join(lines)
