"""
Datum Detection Engine — deterministic workholding datum face selection.

Produces DatumCandidates with primary, secondary, and tertiary datum faces
following the 3-2-1 locating principle.

THE 3-2-1 LOCATING PRINCIPLE
==============================
Any rigid body in 3D has 6 degrees of freedom (3 translations + 3 rotations).
To fully constrain a workpiece, fixtures remove these DOF:
  • Primary datum (3 DOF removed): The part sits on a large flat surface.
    This constrains Z-translation + X-rotation + Y-rotation.
  • Secondary datum (2 DOF removed): A perpendicular face contacts a fence.
    This constrains Y-translation + Z-rotation.
  • Tertiary datum (1 DOF removed): A third perpendicular face contacts a stop.
    This constrains X-translation.

WHY THE LARGEST PLANAR FACE IS THE BEST PRIMARY DATUM
======================================================
  1. Maximum contact area → distributes clamping force, prevents local deformation
  2. Minimizes deflection during cutting (more supported material)
  3. Reduces chatter — part's natural frequency ∝ sqrt(support stiffness)
  4. Simplifies setup — large flat surfaces are easy to indicate and clamp

WHY SMALL FACES ARE REJECTED (AREA < 5% OF LARGEST)
=====================================================
  1. Small faces provide insufficient clamping contact area
  2. Tooling marks and burrs on small faces create poor datum surfaces
  3. Measurement uncertainty is proportionally higher on small surfaces
  4. Vise jaw contact on a small face causes point loading → deformation

DATUM SELECTION ALGORITHM
=========================
  1. Filter topology graph for PLANAR faces with area > 5% of max area
  2. Score each candidate:
     - Area contribution (weight 0.4, normalized against max area)
     - Z-alignment |n̂ · ẑ| (weight 0.3, horizontal = good for gravity clamping)
     - Low Z-center (weight 0.3, gravity-favorable position)
  3. Select primary = highest score
  4. Secondary = largest remaining planar face perpendicular to primary
  5. Tertiary = largest remaining planar face perpendicular to both
  6. Tie-breaking: if two faces have scores within tolerance,
     select the one with the lower face ID for deterministic results

ENGINEERING RULES
=================
  • Pure function — no side effects, no DB writes
  • Uses TopologyGraph only — no OCC dependency
  • Always produces at least a primary datum
  • All normals normalized before dot products
  • Reasoning string includes ranking score for traceability
  • Tolerance = 1e-6 for all float comparisons
"""

from __future__ import annotations

import logging
import math
import time

from cad_worker.schemas import DatumCandidates, TopologyGraph

logger = logging.getLogger("cad_worker.datum_detector")

_TOLERANCE = 1e-6

# Faces with area below this fraction of the max area are rejected.
# 5% ensures only structurally significant faces are considered as datums.
_AREA_REJECTION_RATIO = 0.05

# Perpendicularity threshold for secondary/tertiary selection.
# |n̂_A · n̂_B| < 0.15 means the faces are within ~8.6° of perpendicular.
_PERPENDICULAR_THRESHOLD = 0.15

# Scoring weights for primary datum candidate ranking.
# Must sum to 1.0. Rationale:
#   Area (0.4): largest impact on clamping stability
#   Z-alignment (0.3): horizontal faces are easiest to clamp
#   Z-center (0.3): lower faces benefit from gravity
_W_AREA = 0.4
_W_Z_ALIGN = 0.3
_W_Z_CENTER = 0.3


def _normalize_vector(
    v: tuple[float, float, float],
) -> tuple[float, float, float]:
    """Normalize to unit length. Returns (0,0,0) if degenerate."""
    mag = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if mag < _TOLERANCE:
        return (0.0, 0.0, 0.0)
    inv = 1.0 / mag
    return (v[0] * inv, v[1] * inv, v[2] * inv)


def _dot(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    """Dot product: a · b."""
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def detect_datums(topology_graph: TopologyGraph) -> DatumCandidates:
    """
    Select datum faces from the topology graph using the 3-2-1 locating principle.

    Args:
        topology_graph: Pre-built topology graph with face classifications.

    Returns:
        DatumCandidates with primary (required), secondary, and tertiary
        face IDs plus reasoning with ranking scores.
    """
    t_start = time.monotonic()

    # ── Guard: empty topology graph ─────────────────────────────────────
    if not topology_graph.faces:
        logger.warning("Empty topology graph — using fallback datum F_001")
        return DatumCandidates(
            primary="F_001",
            secondary=None,
            tertiary=None,
            reasoning="No faces in topology graph. Fallback datum.",
        )

    # ── Step 1: Filter PLANAR faces with area > rejection threshold ─────
    planar_faces = [
        f for f in topology_graph.faces
        if f.surface_type == "PLANAR" and f.area > _TOLERANCE
    ]

    if not planar_faces:
        logger.warning("No planar faces found — using first face as fallback datum")
        fallback_id = topology_graph.faces[0].id
        return DatumCandidates(
            primary=fallback_id,
            secondary=None,
            tertiary=None,
            reasoning=(
                f"No planar faces detected. "
                f"Using first face {fallback_id} as primary datum."
            ),
        )

    # Sort by area descending for consistent processing
    planar_faces.sort(key=lambda f: f.area, reverse=True)
    max_area = planar_faces[0].area

    # Reject small faces (< 5% of max area)
    candidates = [
        f for f in planar_faces
        if f.area > max_area * _AREA_REJECTION_RATIO
    ]

    if not candidates:
        # All faces are small — use the largest one
        candidates = [planar_faces[0]]

    # ── Step 2: Score and rank candidates ────────────────────────────────
    def _primary_score(face) -> tuple[float, str]:
        """
        Score a face for primary datum suitability.

        Returns (score, face_id) — face_id breaks ties deterministically.
        """
        # Area contribution (normalized)
        area_score = face.area / max_area if max_area > _TOLERANCE else 0.0

        # Z-alignment: |n̂ · ẑ| close to 1.0 means face is horizontal
        n = _normalize_vector(face.normal)
        z_alignment = abs(n[2])  # |n_z|

        # Low Z-center: lower Z = higher score (gravity-favorable)
        # Use sigmoid-like decreasing function:
        #   score = 1 / (1 + max(0, z_center))
        # This maps z=0 → score=1.0, z=100 → score≈0.01
        z_center = face.center[2]
        z_score = 1.0 / (1.0 + max(0.0, z_center))

        total = _W_AREA * area_score + _W_Z_ALIGN * z_alignment + _W_Z_CENTER * z_score
        return total

    scored = [(f, _primary_score(f)) for f in candidates]
    # Sort by score descending, then face ID ascending (deterministic tie-breaking)
    scored.sort(key=lambda x: (-x[1], x[0].id))

    primary = scored[0][0]
    primary_score = scored[0][1]
    primary_normal = _normalize_vector(primary.normal)

    reasoning_parts = [
        f"Primary: {primary.id} (score={primary_score:.3f}, "
        f"area={primary.area:.2f}mm², "
        f"normal=({primary.normal[0]:.3f},{primary.normal[1]:.3f},{primary.normal[2]:.3f}), "
        f"z={primary.center[2]:.2f})."
    ]

    # ── Step 3: Secondary datum (perpendicular to primary) ──────────────
    secondary = None
    remaining = [f for f in planar_faces if f.id != primary.id
                 and f.area > max_area * _AREA_REJECTION_RATIO]
    # Sort remaining by area descending for largest-first selection
    remaining.sort(key=lambda f: f.area, reverse=True)

    for face in remaining:
        fn = _normalize_vector(face.normal)
        if fn == (0.0, 0.0, 0.0):
            continue
        dot = _dot(primary_normal, fn)
        if abs(dot) < _PERPENDICULAR_THRESHOLD:
            secondary = face
            reasoning_parts.append(
                f"Secondary: {face.id} (perp to primary, "
                f"dot={dot:.4f}, area={face.area:.2f}mm²)."
            )
            break

    # ── Step 4: Tertiary datum (perpendicular to both) ──────────────────
    tertiary = None
    if secondary is not None:
        secondary_normal = _normalize_vector(secondary.normal)
        remaining2 = [f for f in remaining if f.id != secondary.id]

        for face in remaining2:
            fn = _normalize_vector(face.normal)
            if fn == (0.0, 0.0, 0.0):
                continue
            dot_p = _dot(primary_normal, fn)
            dot_s = _dot(secondary_normal, fn)
            if abs(dot_p) < _PERPENDICULAR_THRESHOLD and abs(dot_s) < _PERPENDICULAR_THRESHOLD:
                tertiary = face
                reasoning_parts.append(
                    f"Tertiary: {face.id} (perp to both, "
                    f"dot_primary={dot_p:.4f}, dot_secondary={dot_s:.4f}, "
                    f"area={face.area:.2f}mm²)."
                )
                break

    if secondary is None:
        reasoning_parts.append("No perpendicular secondary found.")
    if tertiary is None and secondary is not None:
        reasoning_parts.append("No tertiary perpendicular to both found.")

    result = DatumCandidates(
        primary=primary.id,
        secondary=secondary.id if secondary else None,
        tertiary=tertiary.id if tertiary else None,
        reasoning=" ".join(reasoning_parts),
    )

    elapsed_ms = (time.monotonic() - t_start) * 1000
    logger.info(
        f"Datum detection complete in {elapsed_ms:.1f}ms: "
        f"primary={result.primary}, secondary={result.secondary}, "
        f"tertiary={result.tertiary}"
    )

    return result
