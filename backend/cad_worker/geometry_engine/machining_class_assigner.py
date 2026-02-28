"""
Machining Class Assigner — assigns machining_class, requires_flip,
and requires_multi_axis to each feature.

MACHINING CLASS ASSIGNMENTS
============================
  HOLE        → DRILL   (hole-making operation)
  POCKET      → ROUGH   (bulk material removal)
  SLOT        → PROFILE (contour-following toolpath)
  CHAMFER     → CHAMFER (dedicated chamfer operation)
  FILLET      → FINISH  (light finishing pass)
  TURN_PROFILE → PROFILE (lathe contour)

SETUP FLAGS
===========
  requires_flip:
    True if the feature's accessibility_direction is opposite to the
    primary datum normal (angle > 90°). Each flip = separate setup.

    Mathematical logic:
      dot(accessibility, datum_normal) < 0 → opposite side → needs flip

  requires_multi_axis:
    True if the feature's axis_direction is NOT aligned with any
    principal axis (X, Y, Z). "Aligned" means max component > 0.9.

    Mathematical logic:
      max(|ax|, |ay|, |az|) < 0.9 → axis is off-principal → multi-axis

Deterministic only. No AI.
"""

from __future__ import annotations

import logging
import math

from cad_worker.schemas import FeatureSpatial, DatumCandidates, TopologyGraph

logger = logging.getLogger("cad_worker.machining_class_assigner")

_TOLERANCE = 1e-6

# ── Machining class lookup ───────────────────────────────────────────────────
# Default class assigned by feature type.
# Phase B may override based on tolerance/surface_finish requirements.
_TYPE_TO_CLASS: dict[str, str] = {
    "HOLE": "DRILL",
    "POCKET": "ROUGH",
    "SLOT": "PROFILE",
    "CHAMFER": "CHAMFER",
    "FILLET": "FINISH",
    "TURN_PROFILE": "PROFILE",
}

# Threshold for "aligned with principal axis".
# cos(26°) ≈ 0.9 — axis must be within 26° of a principal direction.
_PRINCIPAL_ALIGNMENT_THRESHOLD = 0.9

# Threshold for "opposite to datum" — dot product below this → needs flip.
# A negative dot product means the feature faces the opposite side of
# the part from the datum. Zero means perpendicular (side access).
_FLIP_DOT_THRESHOLD = 0.0


def assign_machining_classes(
    features: list[FeatureSpatial],
    datum_candidates: DatumCandidates,
    topology_graph: TopologyGraph,
) -> list[FeatureSpatial]:
    """
    Assign machining_class, requires_flip, and requires_multi_axis
    to each feature based on type, axis, and datum context.

    Args:
        features: List of spatially-mapped features.
        datum_candidates: Datum faces for flip detection.
        topology_graph: Topology graph for datum normal lookup.

    Returns:
        New list of FeatureSpatial with machining metadata populated.
    """
    logger.info(f"Assigning machining classes to {len(features)} features")

    # ── Look up primary datum normal ────────────────────────────────────
    datum_normal = _get_datum_normal(datum_candidates, topology_graph)

    result: list[FeatureSpatial] = []
    flip_count = 0
    multi_axis_count = 0

    for feat in features:
        updates: dict = {}

        # ── Machining class ─────────────────────────────────────────────
        mc = _TYPE_TO_CLASS.get(feat.type, "ROUGH")

        # Threaded holes get THREAD class instead of DRILL
        if feat.type == "HOLE" and feat.hole_subtype == "THREADED":
            mc = "THREAD"

        updates["machining_class"] = mc

        # ── Requires flip ───────────────────────────────────────────────
        needs_flip = _check_requires_flip(feat, datum_normal)
        updates["requires_flip"] = needs_flip
        if needs_flip:
            flip_count += 1

        # ── Requires multi-axis ─────────────────────────────────────────
        needs_multi = _check_requires_multi_axis(feat)
        updates["requires_multi_axis"] = needs_multi
        if needs_multi:
            multi_axis_count += 1

        result.append(feat.model_copy(update=updates))

    logger.info(
        f"Machining classes assigned: "
        f"{flip_count} require flip, "
        f"{multi_axis_count} require multi-axis"
    )

    return result


# ── Internal helpers ─────────────────────────────────────────────────────────

def _get_datum_normal(
    datum: DatumCandidates,
    topology: TopologyGraph,
) -> tuple[float, float, float]:
    """
    Look up the primary datum face normal from the topology graph.

    Falls back to Z-up (0, 0, 1) if the datum face is not found.
    """
    for face in topology.faces:
        if face.id == datum.primary:
            return face.normal

    logger.warning(
        f"Primary datum face {datum.primary} not found in topology. "
        f"Falling back to Z-up normal."
    )
    return (0.0, 0.0, 1.0)


def _check_requires_flip(
    feat: FeatureSpatial,
    datum_normal: tuple[float, float, float],
) -> bool:
    """
    Check if the feature requires a part flip (different setup).

    Mathematical logic:
        dot(accessibility_direction, datum_normal)
        If < 0 → feature faces opposite side from datum → needs flip
        If = 0 → side access (perpendicular) → no flip needed for 3-axis
        If > 0 → same side as datum → no flip

    A flip means the part must be re-clamped, re-probed, and
    re-referenced — typically adding 15-30 minutes to cycle time.
    """
    ax = feat.accessibility_direction
    dot = (
        ax[0] * datum_normal[0]
        + ax[1] * datum_normal[1]
        + ax[2] * datum_normal[2]
    )
    return dot < _FLIP_DOT_THRESHOLD


def _check_requires_multi_axis(feat: FeatureSpatial) -> bool:
    """
    Check if the feature axis requires 4-axis or 5-axis machining.

    Mathematical logic:
        A feature is 3-axis compatible if its axis_direction is aligned
        with one of the 6 principal directions (±X, ±Y, ±Z).

        "Aligned" means max(|ax|, |ay|, |az|) > 0.9.

        If no principal alignment exists, the feature needs a rotary
        axis (4-axis) or full simultaneous control (5-axis).
    """
    ax, ay, az = feat.axis_direction

    # Normalize
    mag = math.sqrt(ax * ax + ay * ay + az * az)
    if mag < _TOLERANCE:
        return False  # Degenerate axis — default to 3-axis

    ax, ay, az = ax / mag, ay / mag, az / mag

    max_component = max(abs(ax), abs(ay), abs(az))
    return max_component < _PRINCIPAL_ALIGNMENT_THRESHOLD
