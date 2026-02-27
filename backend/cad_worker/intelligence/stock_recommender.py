"""
Stock Recommendation Engine — deterministic raw stock type and size suggestion.

Produces a StockRecommendation containing:
  • Stock type: PLATE, BAR, or BLOCK
  • Stock dimensions (bounding box + allowance)
  • Allowance per face (default 2mm)

CYLINDRICAL DOMINANCE DETECTION (AREA-WEIGHTED)
=================================================
A part is classified as cylindrical-dominant (BAR stock) when the
SURFACE AREA of cylindrical faces exceeds 60% of total surface area.

Why area-weighted ratio instead of face count:
  Face count is misleading because:
  • A single large cylindrical bore has 1 face but dominates the geometry
  • Small decorative chamfers/fillets add many faces but negligible area
  • Face subdivision by OCC (BSpline approximations) artificially inflates count

  Area ratio correctly reflects the volumetric dominance of cylindrical geometry:
    R_cyl = Σ(area of CYLINDRICAL faces) / Σ(area of ALL faces)
    If R_cyl > 0.60 → cylindrical-dominant

  Threshold 0.60 (not 0.70):
    Lowered from 0.70 because area-weighted ratios are naturally lower than
    face-count ratios — a 25mm fillet has large face count but moderate area.
    0.60 was calibrated against typical lathe parts (shafts, bushings, flanges).

AXIS SYMMETRY DETECTION
========================
After confirming cylindrical dominance, we check for rotational symmetry:
  • Collect planar face normals (end faces of cylindrical parts)
  • Cluster normals by direction (parallel/anti-parallel)
  • If the dominant cluster contains >50% of planar normals → axisymmetric
  • This means the part can be turned on a lathe → BAR stock

PLATE DETECTION
================
A part is classified as PLATE when:
  height / length < 0.25 (strict less-than)
  height is the smallest AABB dimension, length is the largest.
  This aspect ratio threshold distinguishes flat sheet-metal-like parts
  from prismatic blocks.

BLOCK (DEFAULT)
================
If neither cylindrical nor plate criteria are met → BLOCK.
This is the safe default — any part can be machined from a block.

ALLOWANCE
==========
Default machining allowance = 2mm per face. This ensures:
  • Enough material for initial facing cuts (datum preparation)
  • Room for workholding (vise jaws contact raw stock, not finished surface)
  • Tolerance for stock size variation (±0.5mm typical for saw-cut stock)

ENGINEERING RULES
=================
  • Pure function — no side effects, no DB writes
  • Uses GeometrySummary (pre-computed) — no OCC dependency
  • TopologyGraph provides face areas and types
  • Guard divide-by-zero in all ratio computations
  • Guard zero-dimension bounding box
  • Tolerance = 1e-6 for all float comparisons
"""

from __future__ import annotations

import logging
import math
import time

from cad_worker.schemas import (
    GeometrySummary,
    StockRecommendation,
    TopologyGraph,
)

logger = logging.getLogger("cad_worker.stock_recommender")

_TOLERANCE = 1e-6

# Default machining allowance per face (mm).
# 2mm provides material for facing, workholding, and stock tolerance.
_DEFAULT_ALLOWANCE = 2.0

# Cylindrical area dominance threshold (fraction of total surface area).
# Lowered from 0.70 (face-count) to 0.60 (area-weighted) — see docstring.
_CYLINDRICAL_AREA_RATIO_THRESHOLD = 0.60

# Axis alignment threshold for symmetry detection.
# cos(11.5°) ≈ 0.98 — normals within 11.5° are considered aligned.
_AXIS_ALIGNMENT_THRESHOLD = 0.98

# Plate aspect ratio threshold: height / length (strict <).
# 0.25 means the smallest dimension is < 25% of the largest → flat part.
_PLATE_ASPECT_THRESHOLD = 0.25


def recommend_stock(
    geometry_summary: GeometrySummary,
    topology_graph: TopologyGraph,
) -> StockRecommendation:
    """
    Recommend raw stock type and dimensions for machining.

    Args:
        geometry_summary: Pre-computed geometry summary with bounding box.
        topology_graph: Pre-built topology graph with face classifications.

    Returns:
        StockRecommendation with type, dimensions, and allowance.
    """
    t_start = time.monotonic()

    bbox = geometry_summary.bounding_box
    allowance = _DEFAULT_ALLOWANCE

    # ── Compute area-weighted cylindrical ratio ─────────────────────────
    total_area = 0.0
    cylindrical_area = 0.0

    for f in topology_graph.faces:
        face_area = max(0.0, f.area)  # Guard negative areas
        total_area += face_area
        if f.surface_type == "CYLINDRICAL":
            cylindrical_area += face_area

    # ── Detect cylindrical dominance ────────────────────────────────────
    stock_type = "BLOCK"  # Default: any part can be machined from a block

    if total_area > _TOLERANCE:
        cyl_ratio = cylindrical_area / total_area

        if cyl_ratio > _CYLINDRICAL_AREA_RATIO_THRESHOLD:
            # Check axis symmetry — are most cylindrical faces coaxial?
            if _has_axis_symmetry(topology_graph):
                stock_type = "BAR"
                logger.info(
                    f"Cylindrical dominance (area): "
                    f"{cyl_ratio:.1%} of surface area, axis-symmetric → BAR"
                )
            else:
                logger.info(
                    f"High cylindrical area ratio ({cyl_ratio:.1%}) but "
                    f"no axis symmetry → BLOCK"
                )
    else:
        logger.warning("Total surface area ≈ 0 — defaulting to BLOCK")

    # ── Detect plate geometry ───────────────────────────────────────────
    if stock_type == "BLOCK":
        # bbox dimensions are sorted: length >= width >= height
        if bbox.length > _TOLERANCE:
            aspect = bbox.height / bbox.length
            if aspect < _PLATE_ASPECT_THRESHOLD:
                stock_type = "PLATE"
                logger.info(
                    f"Plate geometry: height/length = {aspect:.3f} "
                    f"< {_PLATE_ASPECT_THRESHOLD} → PLATE"
                )
        else:
            logger.warning("Bounding box length ≈ 0 — defaulting to BLOCK")

    # ── Compute stock dimensions with allowance ─────────────────────────
    # Add 2x allowance per axis (one per face on each side)
    stock_length = round(bbox.length + 2 * allowance, 6)
    stock_width = round(bbox.width + 2 * allowance, 6)
    stock_height = round(bbox.height + 2 * allowance, 6)

    result = StockRecommendation(
        type=stock_type,
        length=stock_length,
        width=stock_width,
        height=stock_height,
        allowance_per_face=allowance,
    )

    elapsed_ms = (time.monotonic() - t_start) * 1000
    logger.info(
        f"Stock recommendation: {stock_type} "
        f"({stock_length}x{stock_width}x{stock_height}mm), "
        f"allowance={allowance}mm/face, "
        f"cyl_area_ratio={cylindrical_area / max(total_area, _TOLERANCE):.1%}, "
        f"elapsed={elapsed_ms:.1f}ms"
    )

    return result


def _has_axis_symmetry(topology_graph: TopologyGraph) -> bool:
    """
    Check if cylindrical faces share a common rotation axis.

    Method: Examine planar face normals — in a rotationally symmetric part,
    the planar end faces have normals that cluster along the rotation axis.

    Algorithm:
      1. Collect normals from PLANAR faces (normalized)
      2. Cluster by direction (parallel or anti-parallel, within tolerance)
      3. If the dominant cluster contains >50% of planar normals → symmetric

    Returns:
        True if axis symmetry is detected.
    """
    planar_normals = []
    for f in topology_graph.faces:
        if f.surface_type == "PLANAR":
            # Normalize the normal vector
            mag = math.sqrt(
                f.normal[0] ** 2 + f.normal[1] ** 2 + f.normal[2] ** 2
            )
            if mag > _TOLERANCE:
                planar_normals.append((
                    f.normal[0] / mag,
                    f.normal[1] / mag,
                    f.normal[2] / mag,
                ))

    if len(planar_normals) < 2:
        return False

    # Cluster normals by direction (parallel or anti-parallel)
    clusters: list[tuple[tuple[float, float, float], int]] = []

    for normal in planar_normals:
        matched = False
        for i, (ref_normal, count) in enumerate(clusters):
            # Cosine similarity — |dot| > threshold means aligned
            dot = abs(
                normal[0] * ref_normal[0]
                + normal[1] * ref_normal[1]
                + normal[2] * ref_normal[2]
            )
            if dot > _AXIS_ALIGNMENT_THRESHOLD:
                clusters[i] = (ref_normal, count + 1)
                matched = True
                break
        if not matched:
            clusters.append((normal, 1))

    if not clusters:
        return False

    max_cluster_size = max(count for _, count in clusters)
    dominant_ratio = max_cluster_size / len(planar_normals)

    return dominant_ratio > 0.5
