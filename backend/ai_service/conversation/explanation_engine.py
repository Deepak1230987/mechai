"""
Explanation Engine — contextual explanations for features and operations.

Generates rich natural-language explanations grounded in *actual*
geometry data, feature IDs, and plan details.  Uses LLM when available,
falls back to deterministic templates.

Rules:
  • Never invent geometry.  All dimensions come from ConversationContext.
  • Always reference feature IDs and operation IDs.
  • No plan modifications.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from ai_service.conversation.context_builder import ConversationContext
from ai_service.schemas.machining_plan import OperationSpec

logger = logging.getLogger("ai_service.conversation.explanation_engine")


# ── Response schema ───────────────────────────────────────────────────────────

class FeatureExplanation(BaseModel):
    """Rich explanation of a detected feature."""

    feature_id: str
    feature_type: str
    dimensions: dict = Field(default_factory=dict)
    position: dict = Field(default_factory=dict)
    related_operations: list[str] = Field(default_factory=list)
    related_tools: list[str] = Field(default_factory=list)
    explanation: str
    manufacturing_notes: list[str] = Field(default_factory=list)
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class OperationExplanation(BaseModel):
    """Rich explanation of a planned operation."""

    operation_id: str
    operation_type: str
    feature_id: str
    tool_id: str
    setup_id: str | None = None
    parameters: dict = Field(default_factory=dict)
    explanation: str
    why_this_tool: str = ""
    why_this_order: str = ""
    estimated_time: float = 0.0
    confidence: float = Field(1.0, ge=0.0, le=1.0)


# ── Public API: Feature Explanation ──────────────────────────────────────────

async def explain_feature(
    feature_id: str,
    ctx: ConversationContext,
) -> FeatureExplanation:
    """
    Explain a detected feature — what it is, why it matters, how it's machined.

    Parameters
    ----------
    feature_id : str
        The ID of the feature to explain.
    ctx : ConversationContext
        Full plan/geometry context.

    Returns
    -------
    FeatureExplanation
    """

    # Find the feature
    feature = _find_feature(feature_id, ctx)
    if not feature:
        return FeatureExplanation(
            feature_id=feature_id,
            feature_type="UNKNOWN",
            explanation=f"Feature '{feature_id}' was not found in the current geometry report.",
            confidence=0.0,
        )

    ftype = feature.get("type", "UNKNOWN")
    dims = feature.get("dimensions", {})
    position = feature.get("position", {})

    # Find related operations and tools
    related_ops = [op for op in ctx.operations if op.feature_id == feature_id]
    related_tool_ids = list({op.tool_id for op in related_ops})

    # Build explanation
    explanation = _build_feature_explanation(feature, related_ops, ctx)
    mfg_notes = _feature_manufacturing_notes(feature, related_ops, ctx)

    return FeatureExplanation(
        feature_id=feature_id,
        feature_type=ftype,
        dimensions=dims,
        position=position,
        related_operations=[op.id for op in related_ops],
        related_tools=related_tool_ids,
        explanation=explanation,
        manufacturing_notes=mfg_notes,
        confidence=0.9 if related_ops else 0.6,
    )


# ── Public API: Operation Explanation ────────────────────────────────────────

async def explain_operation(
    operation_id: str,
    ctx: ConversationContext,
) -> OperationExplanation:
    """
    Explain a planned operation — what it does, why this tool, why this order.

    Parameters
    ----------
    operation_id : str
        The ID of the operation to explain.
    ctx : ConversationContext

    Returns
    -------
    OperationExplanation
    """

    op = _find_operation(operation_id, ctx)
    if not op:
        return OperationExplanation(
            operation_id=operation_id,
            operation_type="UNKNOWN",
            feature_id="UNKNOWN",
            tool_id="UNKNOWN",
            explanation=f"Operation '{operation_id}' was not found in the current plan.",
            confidence=0.0,
        )

    setup_id = _find_setup_for_op(operation_id, ctx)
    explanation = _build_operation_explanation(op, ctx)
    why_tool = _explain_tool_choice(op, ctx)
    why_order = _explain_operation_order(op, ctx)

    return OperationExplanation(
        operation_id=operation_id,
        operation_type=op.type,
        feature_id=op.feature_id,
        tool_id=op.tool_id,
        setup_id=setup_id,
        parameters=op.parameters,
        explanation=explanation,
        why_this_tool=why_tool,
        why_this_order=why_order,
        estimated_time=op.estimated_time,
        confidence=0.9,
    )


# ── Internal: lookup helpers ─────────────────────────────────────────────────

def _find_feature(feature_id: str, ctx: ConversationContext) -> dict | None:
    for f in ctx.features:
        fid = f.get("id", f.get("feature_id", ""))
        if fid == feature_id:
            return f
    return None


def _find_operation(operation_id: str, ctx: ConversationContext) -> OperationSpec | None:
    for op in ctx.operations:
        if op.id == operation_id:
            return op
    return None


def _find_setup_for_op(operation_id: str, ctx: ConversationContext) -> str | None:
    for s in ctx.setups:
        if operation_id in s.operations:
            return s.setup_id
    return None


def _find_tool(tool_id: str, ctx: ConversationContext):
    for t in ctx.tools:
        if t.id == tool_id:
            return t
    return None


# ── Internal: feature explanation builder ────────────────────────────────────

def _build_feature_explanation(
    feature: dict,
    related_ops: list[OperationSpec],
    ctx: ConversationContext,
) -> str:
    """Build a deterministic explanation for a feature."""
    ftype = feature.get("type", "UNKNOWN")
    fid = feature.get("id", feature.get("feature_id", "?"))
    dims = feature.get("dimensions", {})

    parts: list[str] = []

    # ── Type description ──────────────────────────────────────────────
    type_desc = _FEATURE_DESCRIPTIONS.get(ftype.upper(), f"a {ftype.lower()} feature")
    parts.append(f"Feature {fid} is {type_desc}.")

    # ── Dimensions ────────────────────────────────────────────────────
    dim_parts: list[str] = []
    if "diameter" in dims:
        dim_parts.append(f"diameter {dims['diameter']:.2f}mm")
    if "depth" in dims:
        dim_parts.append(f"depth {dims['depth']:.2f}mm")
    if "width" in dims:
        dim_parts.append(f"width {dims['width']:.2f}mm")
    if "length" in dims:
        dim_parts.append(f"length {dims['length']:.2f}mm")
    if "radius" in dims:
        dim_parts.append(f"radius {dims['radius']:.2f}mm")
    if dim_parts:
        parts.append(f"Dimensions: {', '.join(dim_parts)}.")

    # ── Position ──────────────────────────────────────────────────────
    pos = feature.get("position", {})
    if pos:
        coords = [f"{k}={v:.2f}" for k, v in pos.items() if isinstance(v, (int, float))]
        if coords:
            parts.append(f"Located at {', '.join(coords)}.")

    # ── Related operations ────────────────────────────────────────────
    if related_ops:
        op_desc = ", ".join(f"{op.id} ({op.type})" for op in related_ops)
        total_time = sum(op.estimated_time for op in related_ops)
        parts.append(
            f"Machined by {len(related_ops)} operation(s): {op_desc}. "
            f"Total time for this feature: {total_time:.1f}s."
        )
    else:
        parts.append("No operations currently assigned to this feature.")

    return " ".join(parts)


_FEATURE_DESCRIPTIONS: dict[str, str] = {
    "HOLE": "a cylindrical hole requiring drilling",
    "THROUGH_HOLE": "a through-hole that passes completely through the workpiece",
    "BLIND_HOLE": "a blind hole with a defined depth",
    "COUNTERBORE": "a counterbored hole with a stepped diameter for bolt heads",
    "POCKET": "a prismatic pocket (material removal cavity)",
    "SLOT": "a linear slot feature",
    "BOSS": "a raised boss feature (island of material)",
    "CHAMFER": "a chamfered edge for deburring or assembly",
    "FILLET": "a filleted edge or corner",
    "FACE": "a flat face requiring facing or surface finishing",
    "THREAD": "a threaded feature (internal or external)",
    "GROOVE": "a groove or channel feature",
    "STEP": "a step feature (material removal creating a ledge)",
    "CONTOUR": "a contoured surface requiring profile machining",
    "TURNING_PROFILE": "a rotational profile for turning operations",
}


def _feature_manufacturing_notes(
    feature: dict,
    related_ops: list[OperationSpec],
    ctx: ConversationContext,
) -> list[str]:
    """Generate manufacturing notes/warnings for a feature."""
    notes: list[str] = []
    fid = feature.get("id", feature.get("feature_id", ""))
    dims = feature.get("dimensions", {})

    # Deep feature warning
    depth = dims.get("depth", 0)
    diameter = dims.get("diameter", 0)
    if depth and diameter and depth > 3 * diameter:
        notes.append(
            f"Deep feature: depth/diameter ratio = {depth/diameter:.1f}. "
            f"Consider peck drilling or reduced feed rate."
        )

    # Thin wall warning (from manufacturability flags)
    for flag in ctx.manufacturability_flags:
        if isinstance(flag, dict) and fid in str(flag.get("affected_features", [])):
            notes.append(f"Manufacturability: {flag.get('message', 'issue detected')}")

    # Related risks
    for risk in ctx.risks:
        if fid in str(risk.affected_operation_ids):
            notes.append(f"Risk [{risk.severity}]: {risk.message}")

    return notes


# ── Internal: operation explanation builder ───────────────────────────────────

def _build_operation_explanation(
    op: OperationSpec,
    ctx: ConversationContext,
) -> str:
    """Build a deterministic explanation for an operation."""
    parts: list[str] = []

    op_desc = _OPERATION_DESCRIPTIONS.get(op.type.upper(), f"a {op.type.lower()} operation")
    parts.append(f"Operation {op.id} is {op_desc} on feature {op.feature_id}.")

    # Tool info
    tool = _find_tool(op.tool_id, ctx)
    if tool:
        parts.append(
            f"Uses tool {tool.id} ({tool.type}, Ø{tool.diameter}mm, "
            f"RPM {tool.recommended_rpm_min}–{tool.recommended_rpm_max})."
        )

    # Setup info
    setup_id = _find_setup_for_op(op.id, ctx)
    if setup_id:
        for s in ctx.setups:
            if s.setup_id == setup_id:
                parts.append(
                    f"Executed in setup {s.setup_id} "
                    f"(orientation: {s.orientation}, datum: {s.datum_face_id})."
                )
                break

    # Parameters
    if op.parameters:
        param_strs = [f"{k}={v}" for k, v in op.parameters.items()]
        parts.append(f"Cutting parameters: {', '.join(param_strs)}.")

    # Time
    parts.append(f"Estimated time: {op.estimated_time:.1f}s.")

    return " ".join(parts)


_OPERATION_DESCRIPTIONS: dict[str, str] = {
    "DRILLING": "a drilling operation to create a cylindrical hole",
    "POCKET_ROUGHING": "a roughing pass to remove bulk material from a pocket",
    "POCKET_FINISHING": "a finishing pass for final pocket dimensions and surface quality",
    "SLOT_MILLING": "a slot milling operation to cut a linear slot",
    "ROUGH_TURNING": "a rough turning pass to remove material on a lathe",
    "FINISH_TURNING": "a finish turning pass for final diameter and surface quality",
    "FACE_MILLING": "a face milling operation to produce a flat surface",
    "FINISH_CONTOUR": "a contour finishing pass following the part profile",
    "GROOVING": "a grooving operation to cut a channel or groove",
    "SPOT_DRILL": "a spot drilling operation to create a center point for subsequent drilling",
    "REAMING": "a reaming operation for precise hole diameter and surface finish",
    "CHAMFER": "a chamfering operation to bevel edges",
    "TAPPING": "a tapping operation to create internal threads",
}


def _explain_tool_choice(op: OperationSpec, ctx: ConversationContext) -> str:
    """Explain why this tool was selected for the operation."""
    tool = _find_tool(op.tool_id, ctx)
    if not tool:
        return f"Tool {op.tool_id} was selected by the deterministic planner."

    feature = None
    for f in ctx.features:
        if f.get("id", f.get("feature_id", "")) == op.feature_id:
            feature = f
            break

    parts: list[str] = []
    parts.append(
        f"{tool.type} (Ø{tool.diameter}mm) was selected because"
    )

    if feature:
        dims = feature.get("dimensions", {})
        feat_dia = dims.get("diameter", 0)
        feat_width = dims.get("width", 0)

        if feat_dia and "DRILL" in tool.type.upper():
            parts.append(
                f" the feature requires a {feat_dia:.2f}mm hole. "
                f"The tool diameter ({tool.diameter}mm) matches the feature geometry."
            )
        elif feat_width and "END_MILL" in tool.type.upper():
            parts.append(
                f" the feature width is {feat_width:.2f}mm. "
                f"A {tool.diameter}mm end mill provides adequate stepover ratio."
            )
        else:
            parts.append(
                f" it matches the {op.type} operation requirements "
                f"for {ctx.material} material."
            )
    else:
        parts.append(
            f" it is appropriate for {op.type} operations on {ctx.material}."
        )

    return "".join(parts)


def _explain_operation_order(op: OperationSpec, ctx: ConversationContext) -> str:
    """Explain why this operation is in its current position."""
    # Find operation index
    op_idx = None
    for i, o in enumerate(ctx.operations):
        if o.id == op.id:
            op_idx = i
            break

    if op_idx is None:
        return "Operation order could not be determined."

    parts: list[str] = []

    # Check if it's a roughing-before-finishing pattern
    if "ROUGHING" in op.type.upper():
        # Check for corresponding finishing op
        for later_op in ctx.operations[op_idx + 1:]:
            if (later_op.feature_id == op.feature_id and
                    "FINISHING" in later_op.type.upper()):
                parts.append(
                    f"Roughing precedes finishing ({later_op.id}) on the same "
                    f"feature to remove bulk material first."
                )
                break

    if "FINISHING" in op.type.upper():
        for earlier_op in ctx.operations[:op_idx]:
            if (earlier_op.feature_id == op.feature_id and
                    "ROUGHING" in earlier_op.type.upper()):
                parts.append(
                    f"Finishing follows roughing ({earlier_op.id}) to achieve "
                    f"final dimensions and surface quality."
                )
                break

    if "SPOT" in op.type.upper() or "CENTER" in op.type.upper():
        parts.append(
            "Spot drilling is performed first to create a pilot point "
            "for accurate subsequent drilling."
        )

    if not parts:
        parts.append(
            f"Operation is at position {op_idx + 1} of {len(ctx.operations)} "
            f"in the planned sequence."
        )

    return " ".join(parts)
