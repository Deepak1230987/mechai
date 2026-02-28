"""
Manufacturability Analyzer — deterministic DFM checks with severity scaling.

Produces ManufacturabilityAnalysis with a list of ManufacturabilityWarning
objects, each identifying a specific geometric concern for manufacturing.

CHECKS AND MATHEMATICAL DEFINITIONS
=====================================

1. THIN WALL — Minimum perpendicular distance between parallel opposing faces
   ────────────────────────────────────────────────────────────────────────────
   Two faces are "parallel opposing" if:
     • Both are PLANAR
     • Normals are anti-parallel: n̂_A · n̂_B ≈ -1.0 (threshold: < -0.95)
   
   The wall thickness is computed as the signed distance between the
   two face planes, projected along face A's normal:
     d_A = n̂_A · c_A   (signed distance from origin to plane A)
     d_B = n̂_A · c_B   (projection of plane B's center onto A's normal)
     thickness = |d_A - d_B|
   
   where c_i is the centroid of face i, and n̂_A is the UNIT normal of face A.
   The normals MUST be normalized before computing the dot product, because
   non-unit normals produce incorrect signed distances.
   
   If thickness < 2.0mm → warning.
   Severity: < 0.5mm → HIGH (risk of punch-through)
             < 1.0mm → HIGH (significant deflection risk)
             < 2.0mm → MEDIUM (marginal, requires careful feeds/speeds)

2. DEEP SLOT — depth / width ratio with 3-tier severity
   ──────────────────────────────────────────────────────
   For features of type SLOT:
     Severity scales with ratio to indicate increasing difficulty:
       ratio > 10 → HIGH   (extreme overhang — EDM likely required)
       ratio > 7  → MEDIUM (long-reach tooling, reduced feeds necessary)
       ratio > 5  → LOW    (approaching limits of standard end mills)
   
   Standard end mills have a maximum L/D (length-to-diameter) ratio of ~4.
   Beyond 5:1 slot depth/width, the tool must be proportionally longer
   than its diameter, causing deflection proportional to (L/D)³.

3. HIGH ASPECT HOLE — depth / diameter ratio with 3-tier severity
   ───────────────────────────────────────────────────────────────
   For features of type HOLE:
     ratio > 15 → HIGH   (gun drilling required, risk of wander)
     ratio > 12 → MEDIUM (peck drilling with coolant-through tooling)
     ratio > 10 → LOW    (deep hole, requires careful chip evacuation)
   
   Standard twist drills can reliably drill to ~5xD without pecking.
   Beyond 10xD, chip evacuation becomes critical — packed chips cause
   drill breakage, poor surface finish, and hole wander.

4. UNDERCUT — Feature accessibility vs primary datum normal
   ─────────────────────────────────────────────────────────
   A feature is an "undercut" if its accessibility direction is not
   reachable from the primary datum orientation. We check:
   
   Step 1: Check if aligned with ANY principal axis (±X, ±Y, ±Z).
           max(|ax_x|, |ax_y|, |ax_z|) < 0.9 → definitely undercut.
   
   Step 2: If aligned with a principal axis, check if that axis is
           compatible with the primary datum. The primary datum normal
           defines the "natural" clamping orientation. If the feature's
           accessibility direction is nearly perpendicular to the datum
           normal (|acc · datum| < 0.1), the feature requires a
           separate setup → flag as potential undercut.
   
   This dual check avoids false positives: a side hole on a prismatic
   block (accessibility = ±X) is NOT an undercut if we can simply
   re-orient the vise. True undercuts are features at oblique angles
   that cannot be reached from any standard 3-axis orientation.

5. SHARP INTERNAL CORNER — Edge length vs minimum tool radius fillet arc
   ──────────────────────────────────────────────────────────────────────
   An internal corner is "sharp" if an edge connecting two perpendicular
   faces has length < π * r_min / 2 (quarter-circle arc length for
   the minimum tool radius fillet, default r_min = 2.0mm).
   
   Why 2.0mm: The smallest standard solid carbide end mill for
   production use is typically ∅4mm (radius 2mm). Smaller tools exist
   but have extremely limited depth of cut (< 2mm) and feed rates,
   making them impractical for most production parts.

ENGINEERING RULES
=================
  • Pure function — no side effects, no DB writes
  • Uses FeatureSpatial and TopologyGraph — no OCC dependency
  • Each check is independent — one failure doesn't skip others
  • All float comparisons use tolerance, never ==
  • All vectors normalized before dot products
  • Severity levels: LOW (informational), MEDIUM (special tooling),
    HIGH (may require fundamentally different process)
  • Tolerance = 1e-6 for all geometric comparisons
"""

from __future__ import annotations

import logging
import math
import time

from cad_worker.schemas import (
    DatumCandidates,
    FeatureSpatial,
    ManufacturabilityAnalysis,
    ManufacturabilityWarning,
    TopologyGraph,
)

logger = logging.getLogger("cad_worker.manufacturability_analyzer")

# Global geometry tolerance
_TOLERANCE = 1e-6

# ── Thin Wall Detection ─────────────────────────────────────────────────────
# Below this thickness (mm), thin wall warning is generated.
_THIN_WALL_MIN_MM = 2.0
# Anti-parallel threshold: normals must satisfy dot < -0.95 (within ~18° of opposed)
_ANTI_PARALLEL_THRESHOLD = -0.95

# ── Deep Slot Detection ─────────────────────────────────────────────────────
# 3-tier severity thresholds for depth/width ratio.
# Beyond 5:1, standard end mills cannot cut reliably.
_DEEP_SLOT_HIGH = 10.0     # ratio > 10 → HIGH (EDM likely required)
_DEEP_SLOT_MEDIUM = 7.0    # ratio > 7  → MEDIUM (long-reach tooling)
_DEEP_SLOT_LOW = 5.0       # ratio > 5  → LOW (approaching limits)

# ── High Aspect Hole Detection ──────────────────────────────────────────────
# 3-tier severity thresholds for depth/diameter ratio.
_HOLE_ASPECT_HIGH = 15.0   # ratio > 15 → HIGH (gun drilling)
_HOLE_ASPECT_MEDIUM = 12.0 # ratio > 12 → MEDIUM (peck drilling)
_HOLE_ASPECT_LOW = 10.0    # ratio > 10 → LOW (careful chip evacuation)

# ── Undercut Detection ──────────────────────────────────────────────────────
# Minimum cosine alignment with any principal axis to be considered "reachable"
_UNDERCUT_PRINCIPAL_THRESHOLD = 0.9
# Minimum cosine alignment with datum normal to avoid separate-setup flag
_UNDERCUT_DATUM_THRESHOLD = 0.1

# ── Sharp Internal Corner Detection ────────────────────────────────────────
# Minimum tool radius (mm) — ∅4mm end mill = 2mm radius.
# This is the smallest practical production tool for most CNC work.
_MIN_TOOL_RADIUS_MM = 2.0
# Perpendicularity threshold: |n_A · n_B| < 0.15 means faces are ~perpendicular
_PERPENDICULAR_THRESHOLD = 0.15

# ── Phase B Enhancement: Deep Blind Hole ────────────────────────────────────
# A BLIND hole with depth/diameter > 10 is extremely hard to machine.
# Chip evacuation fails, drill wander increases, breakage risk is high.
_DEEP_BLIND_HOLE_THRESHOLD = 10.0

# ── Phase B Enhancement: Small Chamfer ──────────────────────────────────────
# Chamfers narrower than 0.5mm need micro-tooling, which is expensive
# and fragile. Most shops reject sub-0.5mm chamfers.
_SMALL_CHAMFER_THRESHOLD_MM = 0.5

# ── Phase B Enhancement: Thin Wall Near Pocket ──────────────────────────────
# If a thin wall is adjacent to a pocket floor, vibration during
# roughing can cause chatter marks and dimensional loss.
_THIN_WALL_NEAR_POCKET_MM = 1.5


def _normalize_vector(
    v: tuple[float, float, float],
) -> tuple[float, float, float]:
    """
    Normalize a 3D vector to unit length.

    Returns (0, 0, 0) if magnitude < _TOLERANCE (degenerate vector).
    """
    mag = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if mag < _TOLERANCE:
        return (0.0, 0.0, 0.0)
    inv = 1.0 / mag
    return (v[0] * inv, v[1] * inv, v[2] * inv)


def _dot(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    """Dot product: a · b = ax*bx + ay*by + az*bz."""
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def analyze(
    features: list[FeatureSpatial],
    topology_graph: TopologyGraph,
    datum_candidates: DatumCandidates | None = None,
) -> ManufacturabilityAnalysis:
    """
    Perform manufacturability analysis on the part geometry.

    Each check runs independently. A failure in one check does not
    prevent other checks from running.

    Args:
        features: Spatially-mapped features from the spatial feature mapper.
        topology_graph: Pre-built topology graph with face data.
        datum_candidates: Optional. If provided, undercut detection uses
            the primary datum normal for improved accuracy.

    Returns:
        ManufacturabilityAnalysis with all detected warnings.
    """
    t_start = time.monotonic()
    warnings: list[ManufacturabilityWarning] = []

    # Resolve primary datum normal for undercut check
    primary_datum_normal: tuple[float, float, float] | None = None
    if datum_candidates is not None:
        for fn in topology_graph.faces:
            if fn.id == datum_candidates.primary:
                primary_datum_normal = _normalize_vector(fn.normal)
                break

    # ── Check 1: Thin Walls ─────────────────────────────────────────────
    try:
        thin_wall_warnings = _check_thin_walls(topology_graph)
        warnings.extend(thin_wall_warnings)
    except Exception as e:
        logger.warning(f"Thin wall check failed: {e}", exc_info=True)

    # ── Check 2: Deep Slots ─────────────────────────────────────────────
    try:
        deep_slot_warnings = _check_deep_slots(features)
        warnings.extend(deep_slot_warnings)
    except Exception as e:
        logger.warning(f"Deep slot check failed: {e}", exc_info=True)

    # ── Check 3: High Aspect Holes ──────────────────────────────────────
    try:
        hole_warnings = _check_high_aspect_holes(features)
        warnings.extend(hole_warnings)
    except Exception as e:
        logger.warning(f"High aspect hole check failed: {e}", exc_info=True)

    # ── Check 4: Undercuts ──────────────────────────────────────────────
    try:
        undercut_warnings = _check_undercuts(features, primary_datum_normal)
        warnings.extend(undercut_warnings)
    except Exception as e:
        logger.warning(f"Undercut check failed: {e}", exc_info=True)

    # ── Check 5: Sharp Internal Corners ─────────────────────────────────
    try:
        corner_warnings = _check_sharp_corners(topology_graph)
        warnings.extend(corner_warnings)
    except Exception as e:
        logger.warning(f"Sharp corner check failed: {e}", exc_info=True)

    # ── Check 6: Deep Blind Holes (Phase B Enhancement) ─────────────────
    try:
        deep_blind_warnings = _check_deep_blind_holes(features)
        warnings.extend(deep_blind_warnings)
    except Exception as e:
        logger.warning(f"Deep blind hole check failed: {e}", exc_info=True)

    # ── Check 7: Small Chamfers (Phase B Enhancement) ───────────────────
    try:
        chamfer_warnings = _check_small_chamfers(features)
        warnings.extend(chamfer_warnings)
    except Exception as e:
        logger.warning(f"Small chamfer check failed: {e}", exc_info=True)

    # ── Check 8: Intersecting Features (Phase B Enhancement) ────────────
    try:
        intersect_warnings = _check_intersecting_features(features)
        warnings.extend(intersect_warnings)
    except Exception as e:
        logger.warning(f"Intersecting features check failed: {e}", exc_info=True)

    elapsed_ms = (time.monotonic() - t_start) * 1000
    high_count = sum(1 for w in warnings if w.severity == "HIGH")
    med_count = sum(1 for w in warnings if w.severity == "MEDIUM")
    low_count = sum(1 for w in warnings if w.severity == "LOW")

    logger.info(
        f"Manufacturability analysis complete in {elapsed_ms:.1f}ms: "
        f"{len(warnings)} warnings "
        f"(HIGH={high_count}, MEDIUM={med_count}, LOW={low_count})"
    )

    return ManufacturabilityAnalysis(warnings=warnings)


# ── Individual checks ────────────────────────────────────────────────────────


def _check_thin_walls(
    topology_graph: TopologyGraph,
) -> list[ManufacturabilityWarning]:
    """
    Detect thin walls by finding parallel opposing planar faces.

    Algorithm complexity: O(n²) where n = number of planar faces.
    For typical machined parts, n < 50, so this is acceptable.
    For very complex parts (n > 200), consider spatial indexing.

    Mathematical method:
      Two planar faces are parallel-opposing if their unit normals satisfy:
        n̂_A · n̂_B < -0.95  (anti-parallel within ~18°)
      Wall thickness = perpendicular distance between the two planes:
        t = |n̂_A · c_A - n̂_A · c_B|
      where n̂_A MUST be unit length for correct distance computation.
    """
    warnings: list[ManufacturabilityWarning] = []
    planar_faces = [
        f for f in topology_graph.faces
        if f.surface_type == "PLANAR" and f.area > _TOLERANCE
    ]

    # O(n²) pairwise comparison — acceptable for n < 200 faces
    for i, face_a in enumerate(planar_faces):
        # Normalize face A's normal for correct distance projection
        n_a = _normalize_vector(face_a.normal)
        if n_a == (0.0, 0.0, 0.0):
            continue  # Skip degenerate normals

        for j in range(i + 1, len(planar_faces)):
            face_b = planar_faces[j]

            # Normalize face B's normal
            n_b = _normalize_vector(face_b.normal)
            if n_b == (0.0, 0.0, 0.0):
                continue

            # Check anti-parallel normals
            dot = _dot(n_a, n_b)
            if dot > _ANTI_PARALLEL_THRESHOLD:
                continue

            # Compute perpendicular distance between planes.
            # Using face A's unit normal as the projection direction:
            #   d_A = n̂_A · c_A  (signed distance from origin to plane A)
            #   d_B = n̂_A · c_B  (projection of B's center onto A's normal)
            #   thickness = |d_A - d_B|
            d_a = _dot(n_a, face_a.center)
            d_b = _dot(n_a, face_b.center)
            thickness = abs(d_a - d_b)

            if thickness < _THIN_WALL_MIN_MM and thickness > _TOLERANCE:
                # 3-tier severity based on thickness
                if thickness < 0.5:
                    severity = "HIGH"  # Risk of punch-through
                elif thickness < 1.0:
                    severity = "HIGH"  # Significant deflection risk
                else:
                    severity = "MEDIUM"  # Marginal, careful feeds needed

                warnings.append(ManufacturabilityWarning(
                    type="THIN_WALL",
                    feature_id=None,
                    severity=severity,
                    reason=(
                        f"Thin wall between {face_a.id} and {face_b.id}: "
                        f"thickness={thickness:.3f}mm "
                        f"(min recommended: {_THIN_WALL_MIN_MM}mm). "
                        f"Risk of deflection and chatter. "
                        f"Normal dot product={dot:.4f}."
                    ),
                ))

    return warnings


def _check_deep_slots(
    features: list[FeatureSpatial],
) -> list[ManufacturabilityWarning]:
    """
    Detect deep slots where depth/width ratio exceeds thresholds.

    3-tier severity scaling:
      > 10 → HIGH   — EDM or custom tooling likely required.
      > 7  → MEDIUM — long-reach end mill with reduced feedrate.
      > 5  → LOW    — approaching standard tooling limits.

    Guard: width must be > _TOLERANCE to prevent divide-by-zero.
    """
    warnings: list[ManufacturabilityWarning] = []

    for feat in features:
        if feat.type != "SLOT":
            continue
        if feat.depth is None or feat.width is None:
            continue
        if feat.width < _TOLERANCE:
            # Zero-width slot — skip to prevent division by zero
            continue

        ratio = feat.depth / feat.width

        if ratio > _DEEP_SLOT_HIGH:
            severity = "HIGH"
        elif ratio > _DEEP_SLOT_MEDIUM:
            severity = "MEDIUM"
        elif ratio > _DEEP_SLOT_LOW:
            severity = "LOW"
        else:
            continue

        warnings.append(ManufacturabilityWarning(
            type="DEEP_SLOT",
            feature_id=feat.id,
            severity=severity,
            reason=(
                f"Deep slot {feat.id}: depth/width={ratio:.1f} "
                f"(thresholds: >{_DEEP_SLOT_LOW} LOW, "
                f">{_DEEP_SLOT_MEDIUM} MEDIUM, >{_DEEP_SLOT_HIGH} HIGH). "
                f"depth={feat.depth:.2f}mm, width={feat.width:.2f}mm. "
                f"Tool deflection ∝ (L/D)³ — long-reach tooling may be needed."
            ),
        ))

    return warnings


def _check_high_aspect_holes(
    features: list[FeatureSpatial],
) -> list[ManufacturabilityWarning]:
    """
    Detect holes with high depth/diameter ratio.

    3-tier severity scaling:
      > 15 → HIGH   — gun drilling required, risk of wander.
      > 12 → MEDIUM — peck drilling with coolant-through tooling.
      > 10 → LOW    — deep hole, careful chip evacuation needed.

    Guard: diameter must be > _TOLERANCE to prevent divide-by-zero.
    """
    warnings: list[ManufacturabilityWarning] = []

    for feat in features:
        if feat.type != "HOLE":
            continue
        if feat.depth is None or feat.diameter is None:
            continue
        if feat.diameter < _TOLERANCE:
            # Zero-diameter hole — skip to prevent division by zero
            continue

        ratio = feat.depth / feat.diameter

        if ratio > _HOLE_ASPECT_HIGH:
            severity = "HIGH"
        elif ratio > _HOLE_ASPECT_MEDIUM:
            severity = "MEDIUM"
        elif ratio > _HOLE_ASPECT_LOW:
            severity = "LOW"
        else:
            continue

        warnings.append(ManufacturabilityWarning(
            type="HIGH_ASPECT_HOLE",
            feature_id=feat.id,
            severity=severity,
            reason=(
                f"High aspect hole {feat.id}: depth/diameter={ratio:.1f} "
                f"(thresholds: >{_HOLE_ASPECT_LOW} LOW, "
                f">{_HOLE_ASPECT_MEDIUM} MEDIUM, >{_HOLE_ASPECT_HIGH} HIGH). "
                f"depth={feat.depth:.2f}mm, diameter={feat.diameter:.2f}mm. "
                f"Chip evacuation becomes critical beyond 10:1."
            ),
        ))

    return warnings


def _check_undercuts(
    features: list[FeatureSpatial],
    primary_datum_normal: tuple[float, float, float] | None = None,
) -> list[ManufacturabilityWarning]:
    """
    Detect features whose accessibility direction requires non-standard setups.

    Two-phase check:
      Phase 1: Is the feature axis aligned with ANY principal axis?
               max(|ax_x|, |ax_y|, |ax_z|) < 0.9 → definitely undercut (HIGH).
      Phase 2: If aligned with a principal axis AND we have a datum normal,
               check if the accessibility direction is compatible with the
               datum orientation. |accessibility · datum_normal| < 0.1 means
               the feature requires a separate setup (MEDIUM).

    This is more machining-aware than simple principal-axis alignment:
    it considers the actual workholding orientation, not just geometry.
    """
    warnings: list[ManufacturabilityWarning] = []

    for feat in features:
        ax = _normalize_vector(feat.axis_direction)
        acc = _normalize_vector(feat.accessibility_direction)

        if ax == (0.0, 0.0, 0.0):
            continue  # Degenerate axis — can't determine accessibility

        # Phase 1: Check alignment with principal axes
        max_alignment = max(abs(ax[0]), abs(ax[1]), abs(ax[2]))

        if max_alignment < _UNDERCUT_PRINCIPAL_THRESHOLD:
            # Axis is at an oblique angle — true undercut
            warnings.append(ManufacturabilityWarning(
                type="UNDERCUT",
                feature_id=feat.id,
                severity="HIGH",
                reason=(
                    f"Undercut {feat.id} ({feat.type}): "
                    f"axis=({ax[0]:.3f}, {ax[1]:.3f}, {ax[2]:.3f}) "
                    f"not aligned with any principal axis "
                    f"(max alignment={max_alignment:.3f}, "
                    f"threshold={_UNDERCUT_PRINCIPAL_THRESHOLD}). "
                    f"Requires 5-axis machining or secondary op."
                ),
            ))
            continue

        # Phase 2: Check compatibility with datum orientation
        if primary_datum_normal is not None and acc != (0.0, 0.0, 0.0):
            datum_alignment = abs(_dot(acc, primary_datum_normal))
            if datum_alignment < _UNDERCUT_DATUM_THRESHOLD:
                warnings.append(ManufacturabilityWarning(
                    type="UNDERCUT",
                    feature_id=feat.id,
                    severity="MEDIUM",
                    reason=(
                        f"Feature {feat.id} ({feat.type}): "
                        f"accessibility=({acc[0]:.3f}, {acc[1]:.3f}, {acc[2]:.3f}) "
                        f"is perpendicular to primary datum normal "
                        f"(alignment={datum_alignment:.3f}). "
                        f"Requires separate setup or part re-orientation."
                    ),
                ))

    return warnings


def _check_sharp_corners(
    topology_graph: TopologyGraph,
) -> list[ManufacturabilityWarning]:
    """
    Detect sharp internal corners by finding short edges between perpendicular faces.

    An internal corner is "sharp" if an edge connecting two perpendicular
    faces has length < π * r_min / 2 (quarter-circle arc length for minimum
    fillet radius, r_min = 2.0mm by default).

    Why π * r / 2:
      A fillet radius r creates a quarter-circle arc at a 90° corner.
      Arc length = π * r / 2. If the edge is shorter than this arc length,
      the fillet (if any) has radius < r_min — a tool of radius r_min
      cannot physically create this corner.

    Guards:
      • Edges with length < _TOLERANCE are skipped (degenerate)
      • Edges with != 2 connected faces are skipped (non-manifold)
      • Face normals are normalized before perpendicularity check
    """
    warnings: list[ManufacturabilityWarning] = []
    # Quarter-circle arc length for minimum tool radius
    min_fillet_arc = math.pi * _MIN_TOOL_RADIUS_MM / 2.0

    # Build face normal lookup with normalized normals
    face_normals: dict[str, tuple[float, float, float]] = {}
    for f in topology_graph.faces:
        face_normals[f.id] = _normalize_vector(f.normal)

    for edge in topology_graph.edges:
        # Only consider manifold edges (exactly 2 connected faces)
        if len(edge.connected_faces) != 2:
            continue
        # Skip degenerate edges
        if edge.length < _TOLERANCE:
            continue
        # Only flag edges shorter than minimum fillet arc
        if edge.length >= min_fillet_arc:
            continue

        f_a_id, f_b_id = edge.connected_faces[0], edge.connected_faces[1]
        n_a = face_normals.get(f_a_id)
        n_b = face_normals.get(f_b_id)

        if n_a is None or n_b is None:
            continue
        # Skip degenerate normals
        if n_a == (0.0, 0.0, 0.0) or n_b == (0.0, 0.0, 0.0):
            continue

        # Check perpendicularity: |n_A · n_B| < 0.15 means ≈ 90° ± 8.6°
        dot = _dot(n_a, n_b)
        if abs(dot) < _PERPENDICULAR_THRESHOLD:
            warnings.append(ManufacturabilityWarning(
                type="SHARP_INTERNAL_CORNER",
                feature_id=None,
                severity="LOW",
                reason=(
                    f"Sharp corner at edge {edge.id} between "
                    f"{f_a_id} and {f_b_id}: "
                    f"edge_length={edge.length:.4f}mm < "
                    f"min_fillet_arc={min_fillet_arc:.4f}mm "
                    f"(for ∅{_MIN_TOOL_RADIUS_MM * 2}mm tool). "
                    f"Face angle dot={dot:.4f}."
                ),
            ))

    return warnings


# ── Phase B Enhancement checks ──────────────────────────────────────────────

def _check_deep_blind_holes(
    features: list[FeatureSpatial],
) -> list[ManufacturabilityWarning]:
    """
    Flag BLIND holes with extreme depth/diameter ratio.

    A blind hole with depth/diameter > 10 is extremely difficult:
      • Chip evacuation fails (chips pack at bottom)
      • Drill wander increases proportionally to depth
      • Breakage risk is HIGH
      • Surface finish degrades

    Only applies to holes with hole_subtype=BLIND (not THROUGH, not COUNTERBORE).
    """
    warnings: list[ManufacturabilityWarning] = []

    for feat in features:
        if feat.type != "HOLE":
            continue
        if feat.hole_subtype != "BLIND":
            continue

        depth = feat.depth or 0.0
        diameter = feat.diameter or 0.0

        if diameter < _TOLERANCE:
            continue

        ratio = depth / diameter
        if ratio > _DEEP_BLIND_HOLE_THRESHOLD:
            warnings.append(ManufacturabilityWarning(
                type="DEEP_BLIND_HOLE",
                feature_id=feat.id,
                severity="HIGH",
                reason=(
                    f"Blind hole {feat.id}: depth/diameter={ratio:.1f} "
                    f"(∅{diameter}mm × {depth}mm deep). "
                    f"Exceeds {_DEEP_BLIND_HOLE_THRESHOLD}:1 — "
                    f"peck drilling with coolant-through required, "
                    f"high breakage risk."
                ),
            ))

    return warnings


def _check_small_chamfers(
    features: list[FeatureSpatial],
) -> list[ManufacturabilityWarning]:
    """
    Flag chamfers that are too narrow for standard tooling.

    Chamfers < 0.5mm width require micro-chamfer tools which:
      • Are expensive (10x standard chamfer mills)
      • Break easily (carbide micro-tools are fragile)
      • Require high-speed spindles (20,000+ RPM)
    """
    warnings: list[ManufacturabilityWarning] = []

    for feat in features:
        if feat.type != "CHAMFER":
            continue

        width = feat.width or 0.0
        if width < _TOLERANCE:
            continue

        if width < _SMALL_CHAMFER_THRESHOLD_MM:
            warnings.append(ManufacturabilityWarning(
                type="SMALL_CHAMFER",
                feature_id=feat.id,
                severity="MEDIUM",
                reason=(
                    f"Chamfer {feat.id}: width={width:.3f}mm "
                    f"< {_SMALL_CHAMFER_THRESHOLD_MM}mm threshold. "
                    f"Requires micro-chamfer tooling (expensive, fragile)."
                ),
            ))

    return warnings


def _check_intersecting_features(
    features: list[FeatureSpatial],
) -> list[ManufacturabilityWarning]:
    """
    Flag features with overlapping bounding volumes.

    Intersecting features increase machining complexity because:
      • Toolpaths must account for material already removed
      • Interrupted cuts cause tool chatter
      • Dimensional accuracy decreases at intersections

    Uses the intersecting_feature_ids populated by the relationship mapper.
    """
    warnings: list[ManufacturabilityWarning] = []
    # Track pairs to avoid duplicate warnings
    warned_pairs: set[tuple[str, str]] = set()

    for feat in features:
        if not feat.intersecting_feature_ids:
            continue

        for other_id in feat.intersecting_feature_ids:
            pair = tuple(sorted([feat.id, other_id]))
            if pair in warned_pairs:
                continue
            warned_pairs.add(pair)

            warnings.append(ManufacturabilityWarning(
                type="INTERSECTING_FEATURES",
                feature_id=feat.id,
                severity="MEDIUM",
                reason=(
                    f"Features {feat.id} ({feat.type}) and {other_id} "
                    f"have overlapping bounding volumes. "
                    f"Toolpath ordering must account for material removal "
                    f"sequence to avoid interrupted cuts."
                ),
            ))

    return warnings
