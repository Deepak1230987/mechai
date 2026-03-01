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

    for op in ctx.operations:
        feature = feature_map.get(op.feature_id, {})
        setup_id = op_to_setup.get(op.id)
        orientation = setup_orient.get(setup_id, "TOP") if setup_id else "TOP"
        tool_axis = _ORIENTATION_TO_AXIS.get(orientation, "Z-")

        # Extract spatial from feature
        centroid = _compute_centroid(feature)
        bb = _compute_feature_bbox(feature)
        depth = _compute_depth(feature, op)

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

    # Handle both formats: {min: [x,y,z], max: [x,y,z]} and {dx, dy, dz}
    if "min" in bbox and "max" in bbox:
        mn = bbox["min"]
        mx = bbox["max"]
        if isinstance(mn, list) and isinstance(mx, list) and len(mn) >= 3 and len(mx) >= 3:
            return BoundingBox3D(
                x_min=mn[0], x_max=mx[0],
                y_min=mn[1], y_max=mx[1],
                z_min=mn[2], z_max=mx[2],
            )

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
