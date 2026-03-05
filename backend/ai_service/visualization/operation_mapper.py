"""
Spatial Operation Mapper — maps operations to 3D coordinates.

Produces a spatial map of every operation:
  • 3D bounding_box of the affected region
  • Setup orientation (which face is "up")
  • Tool approach axis
  • Feature centroid position
  • Depth / Z-range

All data comes from the topology_graph + feature spatial data in the
intelligence report.  **No LLM**.  Pure geometry math.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from pydantic import BaseModel, Field

from ai_service.conversation.context_builder import ConversationContext

logger = logging.getLogger("ai_service.visualization.operation_mapper")


# ── Schemas ───────────────────────────────────────────────────────────────────

class BoundingBox3D(BaseModel):
    """Axis-aligned bounding box in model coordinates."""

    x_min: float = 0.0
    x_max: float = 0.0
    y_min: float = 0.0
    y_max: float = 0.0
    z_min: float = 0.0
    z_max: float = 0.0


class SpatialOperation(BaseModel):
    """Spatial metadata for a single operation."""

    operation_id: str
    feature_id: str
    operation_type: str
    setup_id: str | None = None
    setup_orientation: str = ""
    tool_axis: str = Field("Z-", description="Tool approach direction e.g. Z-, X+, Y-")
    centroid: dict = Field(default_factory=dict, description="{'x': ..., 'y': ..., 'z': ...}")
    bounding_box: BoundingBox3D = Field(default_factory=BoundingBox3D)
    depth: float = Field(0.0, description="Cut depth from surface (mm)")
    tool_id: str = ""
    tool_diameter: float = 0.0
    estimated_time: float = 0.0


class SpatialOperationMap(BaseModel):
    """Complete spatial map of all operations in the plan."""

    model_id: str
    plan_id: str | None = None
    version: int = 1
    total_operations: int = 0
    spatial_operations: list[SpatialOperation] = Field(default_factory=list)
    part_bounding_box: BoundingBox3D = Field(default_factory=BoundingBox3D)
    setup_orientations: list[dict] = Field(default_factory=list)


# ── Orientation → tool axis mapping ──────────────────────────────────────────

_ORIENTATION_TO_AXIS: dict[str, str] = {
    "TOP": "Z-",
    "BOTTOM": "Z+",
    "FRONT": "Y-",
    "BACK": "Y+",
    "LEFT": "X+",
    "RIGHT": "X-",
    "CHUCK_Z": "Z-",
    "CHUCK_X": "X-",
}


# ── Public API ────────────────────────────────────────────────────────────────

def map_operations_spatial(ctx: ConversationContext) -> SpatialOperationMap:
    """
    Build a spatial map of all operations from context.

    Parameters
    ----------
    ctx : ConversationContext
        Fully assembled context with features, operations, setups, topology.

    Returns
    -------
    SpatialOperationMap
        Each operation enriched with spatial data.
    """

    # ── Build feature lookup ─────────────────────────────────────────────
    feature_map: dict[str, dict] = {}
    for f in ctx.features:
        fid = f.get("id", f.get("feature_id", ""))
        if fid:
            feature_map[fid] = f

    # ── Build setup lookup ───────────────────────────────────────────────
    op_to_setup: dict[str, str] = {}
    setup_orient: dict[str, str] = {}
    for s in ctx.setups:
        setup_orient[s.setup_id] = s.orientation
        for op_id in s.operations:
            op_to_setup[op_id] = s.setup_id

    # ── Build tool lookup ────────────────────────────────────────────────
    tool_map: dict[str, Any] = {}
    for t in ctx.tools:
        tool_map[t.id] = t

    # ── Extract part bounding box from geometry_summary ──────────────────
    part_bb = _extract_part_bbox(ctx.geometry_summary)

    # ── Map each operation ───────────────────────────────────────────────
    spatial_ops: list[SpatialOperation] = []
    op_count = len(ctx.operations)

    for op_idx, op in enumerate(ctx.operations):
        feature = feature_map.get(op.feature_id, {})
        setup_id = op_to_setup.get(op.id)
        orientation = setup_orient.get(setup_id, "TOP") if setup_id else "TOP"
        tool_axis = _ORIENTATION_TO_AXIS.get(orientation, "Z-")

        # Extract spatial from feature — with fallback to part bbox + op params
        if feature and _has_spatial_data(feature):
            centroid = _compute_centroid(feature)
            bb = _compute_feature_bbox(feature)
            depth = _compute_depth(feature, op)
        else:
            # Derive spatial data from operation type, params, and part bbox
            centroid, bb, depth = _derive_spatial_from_operation(
                op, part_bb, orientation, op_idx, op_count,
            )

        # Tool info
        tool = tool_map.get(op.tool_id)
        tool_diameter = tool.diameter if tool else 0.0

        spatial_ops.append(SpatialOperation(
            operation_id=op.id,
            feature_id=op.feature_id,
            operation_type=op.type,
            setup_id=setup_id,
            setup_orientation=orientation,
            tool_axis=tool_axis,
            centroid=centroid,
            bounding_box=bb,
            depth=depth,
            tool_id=op.tool_id,
            tool_diameter=tool_diameter,
            estimated_time=op.estimated_time,
        ))

    # ── Setup orientation summary ────────────────────────────────────────
    setup_summaries = [
        {
            "setup_id": s.setup_id,
            "orientation": s.orientation,
            "datum_face_id": s.datum_face_id,
            "tool_axis": _ORIENTATION_TO_AXIS.get(s.orientation, "Z-"),
            "operation_count": len(s.operations),
        }
        for s in ctx.setups
    ]

    result = SpatialOperationMap(
        model_id=ctx.model_id,
        plan_id=ctx.plan_id,
        version=ctx.version,
        total_operations=len(spatial_ops),
        spatial_operations=spatial_ops,
        part_bounding_box=part_bb,
        setup_orientations=setup_summaries,
    )

    logger.info(
        "Mapped %d operations spatially for model=%s",
        len(spatial_ops), ctx.model_id,
    )
    return result


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_part_bbox(geometry_summary: dict) -> BoundingBox3D:
    """Extract part bounding box from geometry summary."""
    bbox = geometry_summary.get("bounding_box", {})
    if not bbox:
        return BoundingBox3D()

    # Format 1: {min: [x,y,z], max: [x,y,z]}
    if "min" in bbox and "max" in bbox:
        mn = bbox["min"]
        mx = bbox["max"]
        if isinstance(mn, list) and isinstance(mx, list) and len(mn) >= 3 and len(mx) >= 3:
            return BoundingBox3D(
                x_min=mn[0], x_max=mx[0],
                y_min=mn[1], y_max=mx[1],
                z_min=mn[2], z_max=mx[2],
            )

    # Format 2: {length, width, height} — from intelligence report
    if "length" in bbox:
        length = float(bbox.get("length", 0))
        width = float(bbox.get("width", 0))
        height = float(bbox.get("height", 0))
        return BoundingBox3D(
            x_min=0, x_max=length,
            y_min=0, y_max=width,
            z_min=0, z_max=height,
        )

    # Format 3: {dx, dy, dz}
    dx = bbox.get("dx", 0)
    dy = bbox.get("dy", 0)
    dz = bbox.get("dz", 0)
    return BoundingBox3D(
        x_min=0, x_max=dx,
        y_min=0, y_max=dy,
        z_min=0, z_max=dz,
    )


def _compute_centroid(feature: dict) -> dict:
    """Compute or extract centroid from feature data."""
    # Direct centroid
    if "centroid" in feature:
        c = feature["centroid"]
        if isinstance(c, dict):
            return c
        if isinstance(c, (list, tuple)) and len(c) >= 3:
            return {"x": c[0], "y": c[1], "z": c[2]}

    # From position
    pos = feature.get("position", {})
    if pos and isinstance(pos, dict):
        return {
            "x": pos.get("x", 0.0),
            "y": pos.get("y", 0.0),
            "z": pos.get("z", 0.0),
        }

    # From bounding box center
    bbox = feature.get("bounding_box", {})
    if bbox:
        mn = bbox.get("min", [0, 0, 0])
        mx = bbox.get("max", [0, 0, 0])
        if isinstance(mn, list) and isinstance(mx, list) and len(mn) >= 3 and len(mx) >= 3:
            return {
                "x": (mn[0] + mx[0]) / 2,
                "y": (mn[1] + mx[1]) / 2,
                "z": (mn[2] + mx[2]) / 2,
            }

    return {"x": 0.0, "y": 0.0, "z": 0.0}


def _compute_feature_bbox(feature: dict) -> BoundingBox3D:
    """Compute bounding box of a feature from its geometry data."""
    bbox = feature.get("bounding_box", {})
    if bbox:
        mn = bbox.get("min", [0, 0, 0])
        mx = bbox.get("max", [0, 0, 0])
        if isinstance(mn, list) and isinstance(mx, list) and len(mn) >= 3 and len(mx) >= 3:
            return BoundingBox3D(
                x_min=mn[0], x_max=mx[0],
                y_min=mn[1], y_max=mx[1],
                z_min=mn[2], z_max=mx[2],
            )

    # Approximate from position + dimensions
    pos = feature.get("position", {})
    dims = feature.get("dimensions", {})
    cx = pos.get("x", 0.0)
    cy = pos.get("y", 0.0)
    cz = pos.get("z", 0.0)

    # For cylindrical features (holes)
    diameter = dims.get("diameter", 0)
    depth = dims.get("depth", 0)
    if diameter:
        r = diameter / 2
        return BoundingBox3D(
            x_min=cx - r, x_max=cx + r,
            y_min=cy - r, y_max=cy + r,
            z_min=cz - depth if depth else cz,
            z_max=cz,
        )

    # For prismatic features (pockets, slots)
    w = dims.get("width", 0)
    length = dims.get("length", w)
    d = dims.get("depth", 0)
    if w:
        return BoundingBox3D(
            x_min=cx - length / 2, x_max=cx + length / 2,
            y_min=cy - w / 2, y_max=cy + w / 2,
            z_min=cz - d if d else cz,
            z_max=cz,
        )

    return BoundingBox3D()


def _compute_depth(feature: dict, op) -> float:
    """Extract cutting depth from feature dimensions or operation params."""
    # From operation parameters
    if op.parameters.get("depth"):
        return float(op.parameters["depth"])
    if op.parameters.get("doc_pct"):
        dims = feature.get("dimensions", {})
        total = dims.get("depth", 0)
        if total:
            return total * float(op.parameters["doc_pct"]) / 100.0

    # From feature dimensions
    dims = feature.get("dimensions", {})
    return float(dims.get("depth", 0))


def _has_spatial_data(feature: dict) -> bool:
    """Check if a feature has enough data to derive spatial coordinates."""
    if feature.get("centroid") or feature.get("position"):
        return True
    bbox = feature.get("bounding_box", {})
    if bbox and ("min" in bbox or "x_min" in bbox):
        return True
    dims = feature.get("dimensions", {})
    if dims and (dims.get("diameter") or dims.get("width") or dims.get("length")):
        return True
    return False


def _derive_spatial_from_operation(
    op,
    part_bb: BoundingBox3D,
    orientation: str,
    op_idx: int,
    op_count: int,
) -> tuple[dict, BoundingBox3D, float]:
    """
    Derive spatial data from operation type & parameters when the
    feature itself has no spatial data (e.g. synthetic features).

    Distributes operations across the part bounding box so each gets
    a distinct visual region.
    """
    params = op.parameters or {}
    op_type = op.type.upper()

    px = part_bb.x_max - part_bb.x_min  # part length (X)
    py = part_bb.y_max - part_bb.y_min  # part width  (Y)
    pz = part_bb.z_max - part_bb.z_min  # part height (Z)

    # Default depth from params
    depth = float(params.get("depth", pz))

    # ── FACE_MILLING: full top surface ────────────────────────────────
    if op_type == "FACE_MILLING":
        # Use the full top face with a small inset for visual clarity
        inset = min(px, py) * 0.05
        bb = BoundingBox3D(
            x_min=part_bb.x_min + inset,
            x_max=part_bb.x_max - inset,
            y_min=part_bb.y_min + inset,
            y_max=part_bb.y_max - inset,
            z_min=part_bb.z_max - depth * 0.6,  # doc_pct
            z_max=part_bb.z_max,
        )
        centroid = {
            "x": (bb.x_min + bb.x_max) / 2,
            "y": (bb.y_min + bb.y_max) / 2,
            "z": part_bb.z_max,
        }
        return centroid, bb, depth

    # ── POCKET_ROUGHING / POCKET_FINISHING: interior region ───────────
    if "POCKET" in op_type:
        margin = min(px, py) * 0.15
        bb = BoundingBox3D(
            x_min=part_bb.x_min + margin,
            x_max=part_bb.x_max - margin,
            y_min=part_bb.y_min + margin,
            y_max=part_bb.y_max - margin,
            z_min=part_bb.z_max - depth,
            z_max=part_bb.z_max - depth * 0.1,
        )
        centroid = {
            "x": (bb.x_min + bb.x_max) / 2,
            "y": (bb.y_min + bb.y_max) / 2,
            "z": part_bb.z_max - depth / 2,
        }
        return centroid, bb, depth

    # ── FINISH_CONTOUR / SLOT_MILLING: perimeter region ──────────────
    if "CONTOUR" in op_type or "SLOT" in op_type:
        wall = min(px, py) * 0.12
        bb = BoundingBox3D(
            x_min=part_bb.x_min,
            x_max=part_bb.x_max,
            y_min=part_bb.y_min,
            y_max=part_bb.y_max,
            z_min=part_bb.z_min,
            z_max=part_bb.z_max,
        )
        # Centroid on the contour edge (front face)
        centroid = {
            "x": part_bb.x_min + px / 2,
            "y": part_bb.y_min,
            "z": part_bb.z_min + pz / 2,
        }
        return centroid, bb, depth

    # ── DRILLING: cylindrical region at varied positions ──────────────
    if "DRILL" in op_type:
        # Spread drill operations across the part
        fraction = (op_idx + 0.5) / max(op_count, 1)
        diameter = float(params.get("diameter", min(px, py) * 0.1))
        r = diameter / 2
        cx = part_bb.x_min + px * fraction
        cy = part_bb.y_min + py / 2
        bb = BoundingBox3D(
            x_min=cx - r, x_max=cx + r,
            y_min=cy - r, y_max=cy + r,
            z_min=part_bb.z_max - depth,
            z_max=part_bb.z_max,
        )
        centroid = {"x": cx, "y": cy, "z": part_bb.z_max}
        return centroid, bb, depth

    # ── TURNING operations: cylindrical envelope ─────────────────────
    if "TURN" in op_type:
        bb = BoundingBox3D(
            x_min=part_bb.x_min,
            x_max=part_bb.x_max,
            y_min=part_bb.y_min + py * 0.1,
            y_max=part_bb.y_max - py * 0.1,
            z_min=part_bb.z_min,
            z_max=part_bb.z_max,
        )
        centroid = {
            "x": (part_bb.x_min + part_bb.x_max) / 2,
            "y": (part_bb.y_min + part_bb.y_max) / 2,
            "z": (part_bb.z_min + part_bb.z_max) / 2,
        }
        return centroid, bb, depth

    # ── Generic fallback: subdivide part along X for each operation ───
    segment_len = px / max(op_count, 1)
    x_start = part_bb.x_min + segment_len * op_idx
    x_end = x_start + segment_len
    bb = BoundingBox3D(
        x_min=x_start, x_max=x_end,
        y_min=part_bb.y_min, y_max=part_bb.y_max,
        z_min=part_bb.z_max - depth, z_max=part_bb.z_max,
    )
    centroid = {
        "x": (x_start + x_end) / 2,
        "y": (part_bb.y_min + part_bb.y_max) / 2,
        "z": part_bb.z_max,
    }
    return centroid, bb, depth
