"""
Industrial PDF Generator — Phase C enhanced PDF report.

Extends the base Phase B ``document_service.generate_plan_pdf`` with:
  • Part Overview (summary stats)
  • Material & Stock comparison
  • Complexity analysis section
  • Detailed Setup Plan with orientation diagrams (text-based)
  • Operations Table with full parameters
  • Tool Library summary
  • Risk Assessment section
  • Detailed Time Breakdown
  • Cost Breakdown
  • Revision History (all versions)
  • Strategy Comparison
  • Manufacturability Analysis

The existing Phase B PDF generator is reused for the core pages.
This module wraps it and adds Phase C-specific sections.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ai_service.conversation.context_builder import ConversationContext
from ai_service.costing.time_simulator import simulate_detailed_time, DetailedTimeBreakdown
from ai_service.costing.cost_estimator import estimate_manufacturing_cost, CostBreakdown

logger = logging.getLogger("ai_service.documentation.pdf_generator")


class IndustrialPDFConfig(BaseModel):
    """Configuration for PDF generation."""

    company_name: str = "MechAI Manufacturing"
    part_name: str = "Unnamed Part"
    include_cost: bool = True
    include_time_breakdown: bool = True
    include_risk_assessment: bool = True
    include_strategy_comparison: bool = True
    include_revision_history: bool = True
    include_manufacturability: bool = True
    approved: bool = False
    approved_by: str | None = None


def generate_industrial_pdf(
    ctx: ConversationContext,
    config: IndustrialPDFConfig | None = None,
    revision_history: list[dict] | None = None,
) -> bytes:
    """
    Generate a comprehensive industrial machining report PDF.

    Uses Phase B's reportlab-based PDF core and adds Phase C sections.

    Parameters
    ----------
    ctx : ConversationContext
    config : IndustrialPDFConfig | None
    revision_history : list[dict] | None
        List of version records for the revision history section.

    Returns
    -------
    bytes
        Raw PDF bytes.
    """
    if config is None:
        config = IndustrialPDFConfig()

    # Compute Phase C analytics
    time_breakdown = simulate_detailed_time(ctx)
    cost_breakdown = estimate_manufacturing_cost(ctx, time_breakdown)

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
        )
    except ImportError:
        logger.error("reportlab not installed — cannot generate PDF")
        raise RuntimeError("reportlab is required for PDF generation")

    buf = io.BytesIO()
    PAGE_W, PAGE_H = A4

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        title=f"Industrial Report — {config.part_name}",
        author=config.company_name,
    )

    ss = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("IRTitle", parent=ss["Title"], fontSize=18, spaceAfter=2 * mm,
                                textColor=colors.HexColor("#1a1a2e")),
        "section": ParagraphStyle("IRSection", parent=ss["Heading2"], fontSize=13,
                                  spaceBefore=6 * mm, spaceAfter=3 * mm,
                                  textColor=colors.HexColor("#16213e")),
        "body": ParagraphStyle("IRBody", parent=ss["Normal"], fontSize=9, leading=13, spaceAfter=2 * mm),
        "small": ParagraphStyle("IRSmall", parent=ss["Normal"], fontSize=7, leading=9,
                                textColor=colors.HexColor("#777777")),
        "table_header": ParagraphStyle("IRTHead", parent=ss["Normal"], fontSize=8,
                                       textColor=colors.white, alignment=TA_CENTER),
        "table_cell": ParagraphStyle("IRTCell", parent=ss["Normal"], fontSize=8,
                                     leading=10, alignment=TA_CENTER),
    }

    elements: list = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ══════════════════════════════════════════════════════════════════════
    # HEADER
    # ══════════════════════════════════════════════════════════════════════
    elements.append(Paragraph(f"<b>{config.company_name}</b>", styles["title"]))
    elements.append(Paragraph(
        f"Industrial Machining Report — {config.part_name} | "
        f"Version {ctx.version} | {now}",
        styles["body"],
    ))
    if not config.approved:
        elements.append(Paragraph(
            '<font color="red"><b>DRAFT — NOT APPROVED</b></font>',
            styles["body"],
        ))
    elements.append(Spacer(1, 4 * mm))

    # ══════════════════════════════════════════════════════════════════════
    # 1. PART OVERVIEW
    # ══════════════════════════════════════════════════════════════════════
    elements.append(Paragraph("<b>1. Part Overview</b>", styles["section"]))
    overview_data = [
        ["Property", "Value"],
        ["Model ID", ctx.model_id[:16] + "…"],
        ["Material", ctx.material],
        ["Machine Type", ctx.machine_type],
        ["Complexity", f"{ctx.complexity_score:.2f} ({ctx.complexity_level})"],
        ["Features", str(len(ctx.features))],
        ["Operations", str(len(ctx.operations))],
        ["Setups", str(len(ctx.setups))],
        ["Strategy", ctx.selected_strategy],
        ["Version", str(ctx.version)],
        ["Rollback", "Yes" if ctx.is_rollback else "No"],
    ]
    t = Table(overview_data, colWidths=[120, 300])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ]))
    elements.append(t)

    # ══════════════════════════════════════════════════════════════════════
    # 2. MATERIAL & STOCK
    # ══════════════════════════════════════════════════════════════════════
    elements.append(Paragraph("<b>2. Material & Stock Preparation</b>", styles["section"]))
    stock = ctx.stock_recommendation
    stock_text = f"Material: <b>{ctx.material}</b>"
    if stock:
        dims = stock.get("dimensions", stock)
        stock_text += f" | Stock: {_fmt_dims(dims)}"
    elements.append(Paragraph(stock_text, styles["body"]))

    # ══════════════════════════════════════════════════════════════════════
    # 3. COMPLEXITY ANALYSIS
    # ══════════════════════════════════════════════════════════════════════
    elements.append(Paragraph("<b>3. Complexity Analysis</b>", styles["section"]))
    elements.append(Paragraph(
        f"Score: <b>{ctx.complexity_score:.2f}</b> "
        f"(Level: <b>{ctx.complexity_level}</b>). "
        f"Multiplier applied to time estimates: "
        f"<b>{time_breakdown.complexity_multiplier:.2f}x</b>.",
        styles["body"],
    ))

    if config.include_manufacturability and ctx.manufacturability_flags:
        elements.append(Paragraph("<i>Manufacturability Flags:</i>", styles["body"]))
        for flag in ctx.manufacturability_flags:
            if isinstance(flag, dict):
                elements.append(Paragraph(
                    f"• [{flag.get('severity', '?')}] {flag.get('code', '?')}: "
                    f"{flag.get('message', '')}",
                    styles["body"],
                ))

    # ══════════════════════════════════════════════════════════════════════
    # 4. SETUP PLAN
    # ══════════════════════════════════════════════════════════════════════
    elements.append(Paragraph("<b>4. Setup Plan</b>", styles["section"]))
    for s in ctx.setups:
        elements.append(Paragraph(
            f"<b>{s.setup_id}</b> — Orientation: {s.orientation}, "
            f"Datum: {s.datum_face_id or 'N/A'}, "
            f"Operations: {len(s.operations)}",
            styles["body"],
        ))

    # ══════════════════════════════════════════════════════════════════════
    # 5. OPERATIONS TABLE
    # ══════════════════════════════════════════════════════════════════════
    elements.append(Paragraph("<b>5. Operations</b>", styles["section"]))
    op_header = ["#", "ID", "Type", "Feature", "Tool", "Time (s)"]
    op_rows = [op_header]
    for i, op in enumerate(ctx.operations, 1):
        op_rows.append([
            str(i),
            op.id[:12],
            op.type,
            op.feature_id[:12],
            op.tool_id[:12],
            f"{op.estimated_time:.1f}",
        ])
    if len(op_rows) > 1:
        op_table = Table(op_rows, colWidths=[25, 75, 90, 75, 75, 50])
        op_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ]))
        elements.append(op_table)

    # ══════════════════════════════════════════════════════════════════════
    # 6. TOOL LIBRARY
    # ══════════════════════════════════════════════════════════════════════
    elements.append(Paragraph("<b>6. Tools</b>", styles["section"]))
    tool_header = ["ID", "Type", "Diameter", "Max Depth", "RPM Range"]
    tool_rows = [tool_header]
    for t in ctx.tools:
        tool_rows.append([
            t.id[:16],
            t.type,
            f"{t.diameter:.1f} mm",
            f"{t.max_depth:.1f} mm",
            f"{t.recommended_rpm_min}–{t.recommended_rpm_max}",
        ])
    if len(tool_rows) > 1:
        tool_table = Table(tool_rows, colWidths=[90, 80, 55, 55, 80])
        tool_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ]))
        elements.append(tool_table)

    # ══════════════════════════════════════════════════════════════════════
    # 7. RISK ASSESSMENT
    # ══════════════════════════════════════════════════════════════════════
    if config.include_risk_assessment:
        elements.append(PageBreak())
        elements.append(Paragraph("<b>7. Risk Assessment</b>", styles["section"]))
        if ctx.risks:
            risk_header = ["Severity", "Code", "Message", "Affected Ops", "Mitigation"]
            risk_rows = [risk_header]
            for r in ctx.risks:
                risk_rows.append([
                    r.severity,
                    r.code,
                    r.message[:40],
                    ", ".join(r.affected_operation_ids[:3]),
                    r.mitigation[:40] if r.mitigation else "—",
                ])
            rt = Table(risk_rows, colWidths=[50, 60, 100, 80, 100])
            rt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#8b0000")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(rt)
        else:
            elements.append(Paragraph("No manufacturing risks identified.", styles["body"]))

    # ══════════════════════════════════════════════════════════════════════
    # 8. TIME BREAKDOWN
    # ══════════════════════════════════════════════════════════════════════
    if config.include_time_breakdown:
        elements.append(Paragraph("<b>8. Time Breakdown</b>", styles["section"]))
        time_data = [
            ["Category", "Value"],
            ["Cutting Time", f"{time_breakdown.total_cutting_time:.1f} s"],
            ["Setup Time", f"{time_breakdown.total_setup_time:.1f} s ({time_breakdown.setup_change_count} changes)"],
            ["Tool Changes", f"{time_breakdown.total_tool_change_time:.1f} s ({time_breakdown.tool_change_count} changes)"],
            ["Strategy Multiplier", f"{time_breakdown.strategy_multiplier:.2f}x ({time_breakdown.strategy})"],
            ["Complexity Multiplier", f"{time_breakdown.complexity_multiplier:.2f}x"],
            ["Total Time", f"{time_breakdown.total_time:.1f} s ({time_breakdown.total_time_minutes:.1f} min)"],
        ]
        tt = Table(time_data, colWidths=[140, 250])
        tt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(tt)

    # ══════════════════════════════════════════════════════════════════════
    # 9. COST BREAKDOWN
    # ══════════════════════════════════════════════════════════════════════
    if config.include_cost:
        elements.append(Paragraph("<b>9. Cost Breakdown</b>", styles["section"]))
        cost_data = [["Category", "Description", "Amount"]]
        for item in cost_breakdown.line_items:
            cost_data.append([
                item.category,
                item.description[:50],
                f"${item.amount:.2f}",
            ])
        cost_data.append(["<b>TOTAL</b>", "", f"<b>${cost_breakdown.total_cost:.2f}</b>"])
        ct = Table(cost_data, colWidths=[80, 220, 60])
        ct.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8e8e8")),
        ]))
        elements.append(ct)

        if cost_breakdown.notes:
            for n in cost_breakdown.notes:
                elements.append(Paragraph(f"<i>Note: {n}</i>", styles["small"]))

    # ══════════════════════════════════════════════════════════════════════
    # 10. STRATEGY COMPARISON
    # ══════════════════════════════════════════════════════════════════════
    if config.include_strategy_comparison and ctx.strategies:
        elements.append(Paragraph("<b>10. Strategy Comparison</b>", styles["section"]))
        strat_header = ["Strategy", "Description", "Est. Time", "Setups", "Ops"]
        strat_rows = [strat_header]
        for s in ctx.strategies:
            marker = " ★" if s.name == ctx.selected_strategy else ""
            strat_rows.append([
                s.name + marker,
                s.description[:40],
                f"{s.estimated_time:.0f}s",
                str(s.setup_count),
                str(s.operation_count),
            ])
        st = Table(strat_rows, colWidths=[80, 140, 60, 40, 40])
        st.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(st)

    # ══════════════════════════════════════════════════════════════════════
    # 11. REVISION HISTORY
    # ══════════════════════════════════════════════════════════════════════
    if config.include_revision_history and revision_history:
        elements.append(Paragraph("<b>11. Revision History</b>", styles["section"]))
        rev_header = ["Version", "Created", "Strategy", "Rollback", "Status"]
        rev_rows = [rev_header]
        for rev in revision_history:
            rev_rows.append([
                str(rev.get("version", "?")),
                str(rev.get("created_at", "?"))[:19],
                rev.get("selected_strategy", "?"),
                "Yes" if rev.get("is_rollback") else "No",
                rev.get("approval_status", "DRAFT"),
            ])
        rv = Table(rev_rows, colWidths=[50, 100, 80, 50, 60])
        rv.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        elements.append(rv)

    # ══════════════════════════════════════════════════════════════════════
    # FOOTER + WATERMARK
    # ══════════════════════════════════════════════════════════════════════
    version_str = f"v{ctx.version}"

    def on_page(canvas, doc_template):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#999999"))
        canvas.drawString(
            15 * mm, 10 * mm,
            f"{config.company_name} | {config.part_name} | {version_str} | "
            f"Page {canvas.getPageNumber()}"
        )
        canvas.drawRightString(
            PAGE_W - 15 * mm, 10 * mm,
            f"Generated {now}",
        )
        if not config.approved:
            canvas.saveState()
            canvas.setFont("Helvetica-Bold", 50)
            canvas.setFillColor(colors.Color(1, 0, 0, alpha=0.08))
            canvas.translate(PAGE_W / 2, PAGE_H / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "DRAFT")
            canvas.restoreState()
        canvas.restoreState()

    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)

    pdf_bytes = buf.getvalue()
    buf.close()
    logger.info(
        "Industrial PDF generated: %s v%d size=%d bytes",
        config.part_name, ctx.version, len(pdf_bytes),
    )
    return pdf_bytes


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_dims(dims: dict) -> str:
    """Format stock dimensions nicely."""
    if not dims:
        return "N/A"
    # Try x/y/z
    x = dims.get("x", dims.get("dx", dims.get("length", 0)))
    y = dims.get("y", dims.get("dy", dims.get("width", 0)))
    z = dims.get("z", dims.get("dz", dims.get("height", 0)))
    if x and y and z:
        return f"{x} × {y} × {z} mm"
    # Try diameter + length
    d = dims.get("diameter", 0)
    l = dims.get("length", 0)
    if d and l:
        return f"Ø{d} × {l} mm"
    return str(dims)
