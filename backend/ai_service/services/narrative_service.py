"""
Narrative Service — LLM-generated manufacturing process narrative.

Produces a professional, human-readable description of the entire
machining plan: material prep, workholding, setup reasoning,
operation-by-operation justification, tool rationale, safety notes,
and post-processing guidance.

The narrative is stored in machining_plans.process_summary (TEXT)
and is independent of the plan_data JSON structure.

Supports graceful fallback: if LLM is unavailable, generates a
deterministic template-based narrative.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from sqlalchemy.ext.asyncio import AsyncSession

from ai_service.models import MachiningPlan
from ai_service.services.langchain_pipeline import _build_llm

logger = logging.getLogger(__name__)


# ── LLM Prompt ────────────────────────────────────────────────────────────────

_NARRATIVE_SYSTEM = """\
You are a senior manufacturing engineer writing a Process Planning Sheet.

Write a professional, structured manufacturing narrative for CNC machining.
Use clear sections with headers. Be specific about parameters.

REQUIRED SECTIONS:
1. Raw Material Selection — material grade, form (bar / plate / billet)
2. Blank Size Recommendation — minimum stock dimensions with allowances
3. Workholding Method — vise, chuck, fixture recommendation with reasoning
4. Setup Instructions — orientation, datum references, alignment notes
5. Operation Sequence — step-by-step with tool, feed/speed, depth rationale
6. Tool Selection Rationale — why each tool was chosen
7. Safety Notes — chip evacuation, coolant, eye protection, clamping checks
8. Post-Processing Notes — deburring, surface finish, inspection points

Write in professional technical English.
Use metric units (mm, mm/min, RPM).
Do NOT use markdown code blocks — use plain section headers with "##".
"""

_NARRATIVE_USER = """\
Material: {material}
Machine type: {machine_type}
Bounding box: {bounding_box}
Volume: {volume} mm³
Surface area: {surface_area} mm²

Machining plan:
{plan_json}

Generate the complete manufacturing narrative.
"""


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_process_narrative(
    plan: MachiningPlan,
    geometry_metadata: dict | None = None,
    session: AsyncSession | None = None,
) -> str:
    """
    Generate and store a manufacturing process narrative.

    Args:
        plan:               MachiningPlan DB row.
        geometry_metadata:  Optional geometry dict (volume, sa, bbox).
        session:            If provided, stores narrative in plan.process_summary.

    Returns:
        The narrative text (markdown-formatted).
    """
    plan_data = plan.plan_data
    material = plan.material
    machine_type = plan.machine_type

    geom = geometry_metadata or {}
    bbox = geom.get("bounding_box", {})
    volume = geom.get("volume", 0)
    surface_area = geom.get("surface_area", 0)

    llm = _build_llm()

    if llm is not None:
        narrative = await _generate_with_llm(
            llm, plan_data, material, machine_type, bbox, volume, surface_area,
        )
    else:
        narrative = _generate_deterministic(
            plan_data, material, machine_type, bbox, volume, surface_area,
        )

    # Persist if session provided
    if session is not None:
        plan.process_summary = narrative
        logger.info(
            "Narrative stored: plan=%s len=%d chars",
            plan.id,
            len(narrative),
        )

    return narrative


# ── LLM path ─────────────────────────────────────────────────────────────────

async def _generate_with_llm(
    llm: Any,
    plan_data: dict,
    material: str,
    machine_type: str,
    bbox: dict,
    volume: float,
    surface_area: float,
) -> str:
    """Generate narrative via LLM. Falls back to deterministic on error."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", _NARRATIVE_SYSTEM),
        ("human", _NARRATIVE_USER),
    ])
    parser = StrOutputParser()
    chain = prompt | llm | parser

    try:
        result = await chain.ainvoke({
            "material": material,
            "machine_type": machine_type,
            "bounding_box": json.dumps(bbox, indent=2, default=str),
            "volume": f"{volume:.1f}",
            "surface_area": f"{surface_area:.1f}",
            "plan_json": json.dumps(plan_data, indent=2, default=str),
        })
        if result and len(result.strip()) > 100:
            logger.info("Narrative generated via LLM (%d chars)", len(result))
            return result.strip()
    except Exception:
        logger.exception("LLM narrative generation failed — using deterministic fallback")

    return _generate_deterministic(
        plan_data, material, machine_type, bbox, volume, surface_area,
    )


# ── Deterministic fallback ───────────────────────────────────────────────────

def _generate_deterministic(
    plan_data: dict,
    material: str,
    machine_type: str,
    bbox: dict,
    volume: float,
    surface_area: float,
) -> str:
    """Template-based narrative when LLM is unavailable."""
    ops = plan_data.get("operations", [])
    tools = {t["id"]: t for t in plan_data.get("tools", [])}
    setups = plan_data.get("setups", [])
    est_time = plan_data.get("estimated_time", 0)

    x = bbox.get("x_size", 0)
    y = bbox.get("y_size", 0)
    z = bbox.get("z_size", 0)

    # Stock allowance: 5mm per side
    stock_x = x + 10 if x else "N/A"
    stock_y = y + 10 if y else "N/A"
    stock_z = z + 10 if z else "N/A"

    lines: list[str] = []

    # ── 1. Material ───────────────────────────────────────────────────────
    lines.append("## 1. Raw Material Selection")
    lines.append("")
    mat_name = material.replace("_", " ").title()
    lines.append(f"Material: **{mat_name}**")
    lines.append(f"Form: Standard plate / bar stock")
    lines.append("")

    # ── 2. Blank size ─────────────────────────────────────────────────────
    lines.append("## 2. Blank Size Recommendation")
    lines.append("")
    lines.append(
        f"Part envelope: {x:.1f} × {y:.1f} × {z:.1f} mm"
        if x else "Part envelope: See model geometry"
    )
    lines.append(
        f"Recommended stock: {stock_x:.1f} × {stock_y:.1f} × {stock_z:.1f} mm "
        f"(+5 mm allowance per side)"
        if isinstance(stock_x, float) else "Recommended stock: Calculate from model geometry + 5 mm allowance per side"
    )
    lines.append(f"Part volume: {volume:.1f} mm³")
    lines.append(f"Surface area: {surface_area:.1f} mm²")
    lines.append("")

    # ── 3. Workholding ────────────────────────────────────────────────────
    lines.append("## 3. Workholding Method")
    lines.append("")
    if machine_type == "LATHE":
        lines.append("- 3-jaw chuck with soft jaws for initial setup")
        lines.append("- Consider collet chuck for finish passes to minimize runout")
    else:
        lines.append("- Machine vise with parallels for prismatic parts")
        lines.append("- Ensure minimum 10 mm clamping engagement")
        lines.append("- Use stop block for repeatability in batch production")
    lines.append("")

    # ── 4. Setup Instructions ─────────────────────────────────────────────
    lines.append("## 4. Setup Instructions")
    lines.append("")
    for i, setup in enumerate(setups, 1):
        sid = setup.get("setup_id", f"S{i}")
        orient = setup.get("orientation", "N/A")
        op_count = len(setup.get("operations", []))
        lines.append(f"**Setup {i}** (ID: {sid})")
        lines.append(f"  - Orientation: {orient}")
        lines.append(f"  - Operations in this setup: {op_count}")
        lines.append(f"  - Verify datum alignment before first cut")
        lines.append("")

    # ── 5. Operation Sequence ─────────────────────────────────────────────
    lines.append("## 5. Operation Sequence")
    lines.append("")
    for i, op in enumerate(ops, 1):
        tool_id = op.get("tool_id", "unknown")
        tool = tools.get(tool_id, {})
        tool_type = tool.get("type", "N/A")
        tool_dia = tool.get("diameter", 0)
        params = op.get("parameters", {})
        depth = params.get("depth", "N/A")
        op_time = op.get("estimated_time", 0)

        lines.append(f"**Op {i}: {op.get('type', 'UNKNOWN')}**")
        lines.append(f"  - Feature: {op.get('feature_id', 'N/A')}")
        lines.append(f"  - Tool: {tool_id} ({tool_type}, Ø{tool_dia} mm)")
        lines.append(f"  - Depth: {depth} mm")
        lines.append(f"  - Estimated time: {op_time:.1f} s")
        lines.append("")

    # ── 6. Tool Rationale ─────────────────────────────────────────────────
    lines.append("## 6. Tool Selection Rationale")
    lines.append("")
    for tid, t in tools.items():
        lines.append(
            f"- **{tid}**: {t.get('type', 'N/A')}, "
            f"Ø{t.get('diameter', 0)} mm, "
            f"max depth {t.get('max_depth', 0)} mm, "
            f"RPM range {t.get('recommended_rpm_min', 0)}-{t.get('recommended_rpm_max', 0)}"
        )
    lines.append("")

    # ── 7. Safety Notes ───────────────────────────────────────────────────
    lines.append("## 7. Safety Notes")
    lines.append("")
    lines.append("- Ensure proper chip evacuation throughout all operations")
    lines.append("- Use flood coolant for aluminum; consider MQL for steel/titanium")
    lines.append("- Verify tool engagement before running at full feed")
    lines.append("- Wear safety glasses and hearing protection")
    lines.append("- Check clamping force before each setup change")
    lines.append("")

    # ── 8. Post-Processing ────────────────────────────────────────────────
    lines.append("## 8. Post-Processing Notes")
    lines.append("")
    lines.append("- Deburr all sharp edges (break edges 0.2-0.5 mm)")
    lines.append("- Inspect critical dimensions per drawing tolerances")
    lines.append("- Clean part with compressed air and solvent wipe")
    lines.append(f"- Total estimated machining time: {est_time:.1f} s ({est_time / 60:.1f} min)")
    lines.append("")

    return "\n".join(lines)
