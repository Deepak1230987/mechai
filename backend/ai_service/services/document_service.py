"""
Document Service — professional PDF export of machining plans.

Uses reportlab to generate process planning sheets suitable for
shop-floor use, RFQ packaging, and compliance audits.

PDF sections:
    • Header (company, part name, version, date)
    • Material & raw stock preparation
    • Setup instructions
    • Operation table
    • Tool list table
    • Estimated machining time
    • Safety notes
    • Process narrative (optional)
    • Signature block
    • Footer with version + page numbers

Draft plans (approved=False) get a diagonal "DRAFT - NOT APPROVED" watermark.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = A4


# ── Public API ────────────────────────────────────────────────────────────────

def generate_plan_pdf(
    plan_data: dict,
    material: str,
    machine_type: str,
    version: int,
    approved: bool,
    approved_by: str | None = None,
    approved_at: datetime | None = None,
    process_summary: str | None = None,
    company_name: str = "MechAI Manufacturing",
    part_name: str = "Unnamed Part",
    include_narrative: bool = True,
) -> bytes:
    """
    Generate a professional PDF process planning sheet.

    Returns raw PDF bytes (application/pdf).
    """
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=25 * mm,
        bottomMargin=20 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        title=f"Process Plan — {part_name}",
        author=company_name,
    )

    styles = _build_styles()
    elements: list = []

    # ── Header ────────────────────────────────────────────────────────────
    elements.extend(_build_header(
        styles, company_name, part_name, material, machine_type,
        version, approved, approved_by, approved_at,
    ))

    # ── Material & Stock ──────────────────────────────────────────────────
    elements.extend(_build_material_section(styles, plan_data, material))

    # ── Setup Instructions ────────────────────────────────────────────────
    elements.extend(_build_setup_section(styles, plan_data))

    # ── Operation Table ───────────────────────────────────────────────────
    elements.extend(_build_operation_table(styles, plan_data))

    # ── Tool List ─────────────────────────────────────────────────────────
    elements.extend(_build_tool_table(styles, plan_data))

    # ── Time Summary ──────────────────────────────────────────────────────
    est_time = plan_data.get("estimated_time", 0)
    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(
        f"<b>Total Estimated Machining Time:</b> {est_time:.1f} s "
        f"({est_time / 60:.1f} min)",
        styles["body"],
    ))

    # ── Safety Notes ──────────────────────────────────────────────────────
    elements.extend(_build_safety_section(styles))

    # ── Process Narrative ─────────────────────────────────────────────────
    if include_narrative and process_summary:
        elements.append(PageBreak())
        elements.extend(_build_narrative_section(styles, process_summary))

    # ── Signature Block ───────────────────────────────────────────────────
    elements.append(Spacer(1, 12 * mm))
    elements.extend(_build_signature_block(styles, approved, approved_by, approved_at))

    # ── Build PDF with page callbacks ─────────────────────────────────────
    watermark = not approved
    version_str = f"v{version}"

    def on_page(canvas, doc_template):
        _draw_footer(canvas, doc_template, version_str, company_name)
        if watermark:
            _draw_watermark(canvas, doc_template)

    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)

    pdf_bytes = buf.getvalue()
    buf.close()

    logger.info(
        "PDF generated: part=%s v%d approved=%s size=%d bytes",
        part_name, version, approved, len(pdf_bytes),
    )
    return pdf_bytes


# ── Styles ────────────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    ss = getSampleStyleSheet()
    custom = {
        "title": ParagraphStyle(
            "PlanTitle",
            parent=ss["Title"],
            fontSize=18,
            spaceAfter=2 * mm,
            textColor=colors.HexColor("#1a1a2e"),
        ),
        "subtitle": ParagraphStyle(
            "PlanSubtitle",
            parent=ss["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#555555"),
            spaceAfter=4 * mm,
        ),
        "section": ParagraphStyle(
            "SectionHeader",
            parent=ss["Heading2"],
            fontSize=13,
            spaceBefore=6 * mm,
            spaceAfter=3 * mm,
            textColor=colors.HexColor("#16213e"),
            borderWidth=0,
            borderPadding=0,
        ),
        "body": ParagraphStyle(
            "PlanBody",
            parent=ss["Normal"],
            fontSize=9,
            leading=13,
            spaceAfter=2 * mm,
        ),
        "small": ParagraphStyle(
            "SmallText",
            parent=ss["Normal"],
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#777777"),
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=ss["Normal"],
            fontSize=8,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=ss["Normal"],
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
        ),
        "table_cell_left": ParagraphStyle(
            "TableCellLeft",
            parent=ss["Normal"],
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
        ),
    }
    return custom


# ── Section builders ──────────────────────────────────────────────────────────

def _build_header(
    styles, company, part, material, machine, version,
    approved, approved_by, approved_at,
) -> list:
    elements = []

    # Title row
    elements.append(Paragraph(company, styles["title"]))

    status_text = (
        f'<font color="green">APPROVED</font> by {approved_by or "N/A"}'
        if approved
        else '<font color="red">DRAFT — NOT APPROVED</font>'
    )

    meta = (
        f"Part: <b>{part}</b> &nbsp;|&nbsp; "
        f"Material: <b>{material.replace('_', ' ')}</b> &nbsp;|&nbsp; "
        f"Machine: <b>{machine.replace('_', ' ')}</b><br/>"
        f"Version: <b>v{version}</b> &nbsp;|&nbsp; "
        f"Date: <b>{datetime.now(timezone.utc).strftime('%Y-%m-%d')}</b> &nbsp;|&nbsp; "
        f"Status: {status_text}"
    )
    elements.append(Paragraph(meta, styles["subtitle"]))

    # Horizontal rule
    hr_data = [["" ]]
    hr = Table(hr_data, colWidths=[PAGE_W - 30 * mm])
    hr.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#16213e")),
    ]))
    elements.append(hr)
    elements.append(Spacer(1, 3 * mm))

    return elements


def _build_material_section(styles, plan_data: dict, material: str) -> list:
    elements = []
    elements.append(Paragraph("Material &amp; Raw Stock Preparation", styles["section"]))

    mat_nice = material.replace("_", " ").title()
    ops = plan_data.get("operations", [])
    # Estimate max depth from operations
    max_depth = 0
    for op in ops:
        d = op.get("parameters", {}).get("depth")
        if d and isinstance(d, (int, float)):
            max_depth = max(max_depth, d)

    lines = [
        f"<b>Material Grade:</b> {mat_nice}",
        f"<b>Stock Form:</b> Standard plate / bar stock",
        f"<b>Max Operation Depth:</b> {max_depth:.1f} mm" if max_depth else "",
        "<b>Pre-machining:</b> Face all reference surfaces; verify stock is square and deburred.",
    ]
    for line in lines:
        if line:
            elements.append(Paragraph(line, styles["body"]))

    return elements


def _build_setup_section(styles, plan_data: dict) -> list:
    elements = []
    setups = plan_data.get("setups", [])
    if not setups:
        return elements

    elements.append(Paragraph("Setup Instructions", styles["section"]))

    for i, setup in enumerate(setups, 1):
        orient = setup.get("orientation", "N/A")
        op_count = len(setup.get("operations", []))
        elements.append(Paragraph(
            f"<b>Setup {i}:</b> Orientation = {orient}, "
            f"Operations = {op_count}. "
            f"Verify workpiece datum alignment before cuts.",
            styles["body"],
        ))

    return elements


def _build_operation_table(styles, plan_data: dict) -> list:
    elements = []
    operations = plan_data.get("operations", [])
    if not operations:
        return elements

    elements.append(Paragraph("Operation Schedule", styles["section"]))

    # Header
    header = ["#", "Type", "Feature", "Tool", "Depth (mm)", "Time (s)"]
    header_row = [Paragraph(f"<b>{h}</b>", styles["table_header"]) for h in header]

    data = [header_row]
    for i, op in enumerate(operations, 1):
        params = op.get("parameters", {})
        depth = params.get("depth", "—")
        if isinstance(depth, (int, float)):
            depth = f"{depth:.1f}"
        est = op.get("estimated_time", 0)

        row = [
            Paragraph(str(i), styles["table_cell"]),
            Paragraph(op.get("type", "N/A"), styles["table_cell_left"]),
            Paragraph(str(op.get("feature_id", "")[:8]) + "…", styles["table_cell"]),
            Paragraph(op.get("tool_id", "N/A"), styles["table_cell"]),
            Paragraph(str(depth), styles["table_cell"]),
            Paragraph(f"{est:.1f}", styles["table_cell"]),
        ]
        data.append(row)

    col_widths = [10 * mm, 40 * mm, 30 * mm, 30 * mm, 25 * mm, 22 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        # Body
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        # Alternating rows
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (1, 1), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(table)

    return elements


def _build_tool_table(styles, plan_data: dict) -> list:
    elements = []
    tools = plan_data.get("tools", [])
    if not tools:
        return elements

    elements.append(Paragraph("Tool List", styles["section"]))

    header = ["Tool ID", "Type", "Diameter (mm)", "Max Depth (mm)", "RPM Range"]
    header_row = [Paragraph(f"<b>{h}</b>", styles["table_header"]) for h in header]

    data = [header_row]
    for t in tools:
        rpm_min = t.get("recommended_rpm_min", 0)
        rpm_max = t.get("recommended_rpm_max", 0)
        row = [
            Paragraph(t.get("id", "N/A"), styles["table_cell_left"]),
            Paragraph(t.get("type", "N/A"), styles["table_cell_left"]),
            Paragraph(f"{t.get('diameter', 0):.1f}", styles["table_cell"]),
            Paragraph(f"{t.get('max_depth', 0):.1f}", styles["table_cell"]),
            Paragraph(f"{rpm_min}–{rpm_max}", styles["table_cell"]),
        ]
        data.append(row)

    col_widths = [30 * mm, 38 * mm, 30 * mm, 30 * mm, 30 * mm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16213e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 1), (1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(table)

    return elements


def _build_safety_section(styles) -> list:
    elements = []
    elements.append(Paragraph("Safety Notes", styles["section"]))

    notes = [
        "Ensure proper chip evacuation throughout all operations.",
        "Use flood coolant for aluminum; consider MQL for steel/titanium alloys.",
        "Verify tool engagement and clamping before running at production feed rates.",
        "Wear safety glasses, hearing protection, and steel-toe footwear.",
        "Check workholding torque before each setup change.",
        "Never reach into the machine envelope while the spindle is running.",
    ]
    for note in notes:
        elements.append(Paragraph(f"• {note}", styles["body"]))

    return elements


def _build_narrative_section(styles, narrative: str) -> list:
    elements = []
    elements.append(Paragraph("Manufacturing Process Narrative", styles["section"]))

    # Convert markdown-ish headers to styled paragraphs
    for line in narrative.split("\n"):
        stripped = line.strip()
        if not stripped:
            elements.append(Spacer(1, 2 * mm))
        elif stripped.startswith("## "):
            elements.append(Spacer(1, 3 * mm))
            elements.append(Paragraph(
                f"<b>{stripped[3:]}</b>",
                styles["body"],
            ))
        elif stripped.startswith("- ") or stripped.startswith("• "):
            elements.append(Paragraph(f"• {stripped[2:]}", styles["body"]))
        elif stripped.startswith("**") and stripped.endswith("**"):
            elements.append(Paragraph(
                f"<b>{stripped[2:-2]}</b>",
                styles["body"],
            ))
        else:
            elements.append(Paragraph(stripped, styles["body"]))

    return elements


def _build_signature_block(styles, approved, approved_by, approved_at) -> list:
    elements = []
    elements.append(Paragraph("Approval &amp; Signatures", styles["section"]))

    sig_data = [
        [
            Paragraph("<b>Prepared By:</b>", styles["body"]),
            "______________________",
            Paragraph("<b>Date:</b>", styles["body"]),
            "_______________",
        ],
        ["", "", "", ""],
        [
            Paragraph("<b>Reviewed By:</b>", styles["body"]),
            "______________________",
            Paragraph("<b>Date:</b>", styles["body"]),
            "_______________",
        ],
        ["", "", "", ""],
        [
            Paragraph("<b>Approved By:</b>", styles["body"]),
            approved_by or "______________________",
            Paragraph("<b>Date:</b>", styles["body"]),
            (approved_at.strftime("%Y-%m-%d") if approved_at else "_______________"),
        ],
    ]

    sig_table = Table(sig_data, colWidths=[30 * mm, 55 * mm, 18 * mm, 40 * mm])
    sig_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    elements.append(sig_table)

    return elements


# ── Page-level callbacks ──────────────────────────────────────────────────────

def _draw_footer(canvas, doc, version_str: str, company: str):
    """Footer: company name left, page number center, version right."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#888888"))

    y = 12 * mm
    canvas.drawString(15 * mm, y, company)
    canvas.drawCentredString(PAGE_W / 2, y, f"Page {canvas.getPageNumber()}")
    canvas.drawRightString(PAGE_W - 15 * mm, y, version_str)

    # Thin line above footer
    canvas.setStrokeColor(colors.HexColor("#cccccc"))
    canvas.setLineWidth(0.5)
    canvas.line(15 * mm, y + 3 * mm, PAGE_W - 15 * mm, y + 3 * mm)

    canvas.restoreState()


def _draw_watermark(canvas, doc):
    """Diagonal 'DRAFT - NOT APPROVED' watermark for unapproved plans."""
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 50)
    canvas.setFillColor(colors.Color(0.85, 0.85, 0.85, alpha=0.5))
    canvas.translate(PAGE_W / 2, PAGE_H / 2)
    canvas.rotate(45)
    canvas.drawCentredString(0, 0, "DRAFT - NOT APPROVED")
    canvas.restoreState()
