"""
Hole Classifier — post-processing pass to assign hole_subtype.

Runs AFTER spatial feature mapping. Takes existing HOLE features and
classifies them into subtypes based on geometric analysis:

  THROUGH      — depth ≈ stock extent along hole axis (within 10%)
  BLIND        — depth < stock extent, no coaxial partner with larger radius
  COUNTERBORE  — two coaxial cylindrical faces with different radii
  COUNTERSINK  — conical face coaxial with cylindrical face
  THREADED     — helical edge pattern on cylindrical face (MVP heuristic)

CLASSIFICATION HIERARCHY
========================
1. First pass: check for coaxial feature pairs (COUNTERBORE, COUNTERSINK)
2. Second pass: single holes classified by depth ratio (THROUGH vs BLIND)
3. Thread detection applied last (refinement of BLIND/THROUGH)

Why this matters for Phase B:
  • THROUGH → standard twist drill, no depth control needed
  • BLIND → peck drilling cycle, chip evacuation strategy
  • COUNTERBORE → 2-operation sequence: drill + counterbore tool
  • COUNTERSINK → 2-operation sequence: drill + countersink tool
  • THREADED → 3-operation sequence: center drill + twist drill + tap

Deterministic only. No AI. No heuristics beyond geometric reasoning.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from cad_worker.schemas import (
    FeatureSpatial,
    GeometrySummary,
    TopologyGraph,
)

logger = logging.getLogger("cad_worker.hole_classifier")

# ── Constants ────────────────────────────────────────────────────────────────

_TOLERANCE = 1e-6

# If depth / stock_extent > this ratio, classify as THROUGH.
# 0.90 accounts for chamfer/fillet material at hole entry/exit.
_THROUGH_DEPTH_RATIO = 0.90

# Maximum distance between two hole axes to be considered coaxial.
# Covers small misalignments from BSpline-classified surfaces.
_COAXIAL_DISTANCE_TOLERANCE = 0.5  # mm

# Maximum angle between axes for coaxial check (in radians).
# cos(5°) ≈ 0.9962 — axes must be nearly parallel.
_COAXIAL_ANGLE_TOLERANCE = 0.1  # radians (~5.7°)

# Minimum radius ratio between outer and inner cylinder for counterbore.
# Outer must be at least 20% larger than inner.
_COUNTERBORE_RADIUS_RATIO = 1.2


def classify_holes(
    features: list[FeatureSpatial],
    geometry_summary: GeometrySummary,
    topology_graph: TopologyGraph,
) -> list[FeatureSpatial]:
    """
    Classify all HOLE features with a hole_subtype.

    This is a post-processing pass — it takes already-mapped FeatureSpatial
    objects and returns new copies with hole_subtype set. Non-HOLE features
    are returned unchanged.

    Args:
        features: List of spatially-mapped features from the mapper.
        geometry_summary: Geometry summary with bounding box for stock extent.
        topology_graph: Topology graph for face type lookups.

    Returns:
        New list of FeatureSpatial with hole_subtype populated for HOLE features.
    """
    start_msg = f"Classifying {sum(1 for f in features if f.type == 'HOLE')} holes"
    logger.info(start_msg)

    # Separate holes from other features
    holes = [f for f in features if f.type == "HOLE"]
    others = [f for f in features if f.type != "HOLE"]

    if not holes:
        logger.info("No holes to classify")
        return features

    # ── Pass 1: Detect coaxial pairs (COUNTERBORE / COUNTERSINK) ────────
    classified_ids: set[str] = set()
    result_holes: list[FeatureSpatial] = []

    coaxial_pairs = _find_coaxial_pairs(holes)
    for pair in coaxial_pairs:
        h_outer, h_inner = pair  # outer has larger diameter
        classified_ids.add(h_outer.id)
        classified_ids.add(h_inner.id)

        # Check if the outer face is conical → COUNTERSINK
        outer_face_type = _get_face_type(h_outer.parent_face_id, topology_graph)
        if outer_face_type == "CONICAL":
            result_holes.append(
                h_outer.model_copy(update={"hole_subtype": "COUNTERSINK"})
            )
            result_holes.append(
                h_inner.model_copy(update={"hole_subtype": "COUNTERSINK"})
            )
            logger.info(
                f"  {h_inner.id}+{h_outer.id} → COUNTERSINK "
                f"(∅{h_inner.diameter}+cone)"
            )
        else:
            # Two cylindrical coaxial faces → COUNTERBORE
            result_holes.append(
                h_outer.model_copy(update={"hole_subtype": "COUNTERBORE"})
            )
            result_holes.append(
                h_inner.model_copy(update={"hole_subtype": "COUNTERBORE"})
            )
            logger.info(
                f"  {h_inner.id}+{h_outer.id} → COUNTERBORE "
                f"(∅{h_inner.diameter}+∅{h_outer.diameter})"
            )

    # ── Pass 2: Single holes → THROUGH or BLIND ─────────────────────────
    bbox = geometry_summary.bounding_box
    stock_extents = (bbox.length, bbox.width, bbox.height)

    for hole in holes:
        if hole.id in classified_ids:
            continue

        subtype = _classify_single_hole(hole, stock_extents)
        result_holes.append(hole.model_copy(update={"hole_subtype": subtype}))
        logger.info(
            f"  {hole.id} → {subtype} "
            f"(∅{hole.diameter}, depth={hole.depth})"
        )

    # ── Pass 3: Thread detection (refine BLIND/THROUGH) ─────────────────
    # MVP: detect based on edge count heuristic on parent face.
    # A threaded hole typically has many more edges than a plain hole
    # due to the helical thread geometry. This is a basic heuristic.
    result_holes = _detect_threaded_holes(result_holes, topology_graph)

    # Combine and preserve original order
    all_features = others + result_holes
    all_features.sort(key=lambda f: f.id)

    logger.info(
        f"Hole classification complete: "
        f"{sum(1 for h in result_holes if h.hole_subtype == 'THROUGH')} THROUGH, "
        f"{sum(1 for h in result_holes if h.hole_subtype == 'BLIND')} BLIND, "
        f"{sum(1 for h in result_holes if h.hole_subtype == 'COUNTERBORE')} COUNTERBORE, "
        f"{sum(1 for h in result_holes if h.hole_subtype == 'COUNTERSINK')} COUNTERSINK, "
        f"{sum(1 for h in result_holes if h.hole_subtype == 'THREADED')} THREADED"
    )

    return all_features


# ── Internal helpers ─────────────────────────────────────────────────────────

def _classify_single_hole(
    hole: FeatureSpatial,
    stock_extents: tuple[float, float, float],
) -> str:
    """
    Classify a single hole as THROUGH or BLIND based on depth vs stock extent.

    The stock extent along the hole axis is computed by projecting the
    bounding box dimensions onto the hole axis direction. This handles
    holes at arbitrary angles, not just principal axes.

    Mathematical logic:
        stock_extent_along_axis = |bbox.length * ax| + |bbox.width * ay| + |bbox.height * az|
        where (ax, ay, az) is the normalized hole axis direction.

        This is the maximum possible extent through the stock along the axis.
        If depth / stock_extent > 0.90, it's a through hole.
    """
    depth = hole.depth or 0.0
    if depth < _TOLERANCE:
        return "BLIND"

    ax, ay, az = hole.axis_direction
    mag = math.sqrt(ax * ax + ay * ay + az * az)
    if mag < _TOLERANCE:
        return "BLIND"

    # Normalize axis
    ax, ay, az = ax / mag, ay / mag, az / mag

    # Project bounding box onto axis direction
    # This gives the stock thickness along the hole axis
    stock_extent = (
        abs(stock_extents[0] * ax)
        + abs(stock_extents[1] * ay)
        + abs(stock_extents[2] * az)
    )

    if stock_extent < _TOLERANCE:
        return "BLIND"

    # Also check the is_through flag set during spatial mapping
    if hole.is_through:
        return "THROUGH"

    depth_ratio = depth / stock_extent
    if depth_ratio >= _THROUGH_DEPTH_RATIO:
        return "THROUGH"

    return "BLIND"


def _find_coaxial_pairs(
    holes: list[FeatureSpatial],
) -> list[tuple[FeatureSpatial, FeatureSpatial]]:
    """
    Find pairs of holes that share the same axis (coaxial).

    Two holes are coaxial if:
      1. Their axis directions are parallel (dot product ≈ ±1)
      2. The perpendicular distance between their axes is < tolerance

    Returns list of (outer, inner) tuples sorted by diameter.

    Mathematical logic:
        Axis parallelism: |dot(a1, a2)| > cos(threshold)
        Perpendicular distance: |cross(a1, p2-p1)| / |a1|
        where p1, p2 are positions on each axis.
    """
    pairs: list[tuple[FeatureSpatial, FeatureSpatial]] = []
    used: set[int] = set()

    for i, h1 in enumerate(holes):
        if i in used:
            continue
        for j, h2 in enumerate(holes):
            if j <= i or j in used:
                continue

            if not _are_coaxial(h1, h2):
                continue

            # Both must have valid diameters
            d1 = h1.diameter or 0.0
            d2 = h2.diameter or 0.0
            if d1 < _TOLERANCE or d2 < _TOLERANCE:
                continue

            # Outer = larger diameter
            if d1 >= d2:
                pairs.append((h1, h2))
            else:
                pairs.append((h2, h1))

            used.add(i)
            used.add(j)
            break  # Each hole pairs with at most one other

    return pairs


def _are_coaxial(h1: FeatureSpatial, h2: FeatureSpatial) -> bool:
    """
    Check if two holes share the same geometric axis.

    Tests:
      1. Axis parallelism via dot product
      2. Perpendicular distance between axis lines
    """
    ax1 = h1.axis_direction
    ax2 = h2.axis_direction

    # Dot product for parallelism
    dot = ax1[0] * ax2[0] + ax1[1] * ax2[1] + ax1[2] * ax2[2]
    if abs(abs(dot) - 1.0) > _COAXIAL_ANGLE_TOLERANCE:
        return False

    # Perpendicular distance = |cross(a1, p2-p1)| / |a1|
    dp = (
        h2.position[0] - h1.position[0],
        h2.position[1] - h1.position[1],
        h2.position[2] - h1.position[2],
    )

    # Cross product of axis1 with displacement
    cx = ax1[1] * dp[2] - ax1[2] * dp[1]
    cy = ax1[2] * dp[0] - ax1[0] * dp[2]
    cz = ax1[0] * dp[1] - ax1[1] * dp[0]

    perp_dist = math.sqrt(cx * cx + cy * cy + cz * cz)
    mag1 = math.sqrt(ax1[0] ** 2 + ax1[1] ** 2 + ax1[2] ** 2)
    if mag1 > _TOLERANCE:
        perp_dist /= mag1

    return perp_dist < _COAXIAL_DISTANCE_TOLERANCE


def _get_face_type(face_id: str, topology: TopologyGraph) -> Optional[str]:
    """Look up a face's surface_type from the topology graph."""
    for face in topology.faces:
        if face.id == face_id:
            return face.surface_type
    return None


def _detect_threaded_holes(
    holes: list[FeatureSpatial],
    topology: TopologyGraph,
) -> list[FeatureSpatial]:
    """
    MVP thread detection: check if a hole's parent face has many edges.

    Rationale:
        A plain cylindrical hole has 2-3 edges (top circle, bottom circle,
        possibly a seam edge). A threaded hole imported from STEP/IGES
        typically has a helical edge that significantly increases the edge
        count on the adjacent topology.

    This is a basic heuristic. Full thread detection requires pitch
    analysis of helical curves, which is Phase C scope.

    Threshold: if a BLIND hole's parent face connects to > 6 edges,
    reclassify as THREADED.
    """
    _THREAD_EDGE_THRESHOLD = 6

    result: list[FeatureSpatial] = []
    for hole in holes:
        # Only refine BLIND holes — through holes are rarely threaded
        # (exception: threaded studs, but those are rare in machined parts)
        if hole.hole_subtype != "BLIND":
            result.append(hole)
            continue

        # Count edges connected to the parent face
        edge_count = 0
        for edge in topology.edges:
            if hole.parent_face_id in edge.connected_faces:
                edge_count += 1

        if edge_count > _THREAD_EDGE_THRESHOLD:
            result.append(hole.model_copy(update={"hole_subtype": "THREADED"}))
            logger.info(
                f"  {hole.id} reclassified BLIND → THREADED "
                f"(edge_count={edge_count} > {_THREAD_EDGE_THRESHOLD})"
            )
        else:
            result.append(hole)

    return result
