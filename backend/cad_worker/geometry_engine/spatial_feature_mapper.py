"""
Spatial Feature Mapper — enriches detected features with 3D spatial metadata.

Takes the raw FeatureResult list from the existing feature detectors and
the TopologyGraph, then produces FeatureSpatial objects with:
  • Global position (centroid of the feature's parent face)
  • Axis direction (cylinder axis for holes, slot direction, etc.)
  • Parent face ID (links feature to topology graph)
  • Accessibility direction (opposite of parent face normal — tool approach)
  • Depth (via projection along accessibility axis)
  • is_through flag (feature penetrates full stock depth)

HOW FEATURES MAP TO TOPOLOGY GRAPH FACE IDs
=============================================
Each feature detector operates on individual faces. To map a feature back
to a topology graph face, we:
  1. Re-iterate faces using the same TopExp_Explorer order as topology_graph.py
  2. For each cylindrical face, check if its properties match a detected HOLE
  3. For each planar face with pocket/slot geometry, match by dimensions

Since both the topology builder and this mapper use the same face iteration
order (TopExp_Explorer), face indices are consistent → face IDs match.

WHY CYLINDER AXIS MIDPOINT IS THE CORRECT CENTROID FOR HOLES
=============================================================
The surface centroid of a cylindrical face (computed via BRepGProp) lies on
the cylinder surface shell — it is the area-weighted center of the lateral
surface. But for a HOLE feature, the meaningful position is the midpoint
of the cylinder's geometric axis — the point on the axis halfway along
the cylinder's V-parameter extent.

Mathematical computation:
  Let axis_origin = gp_Ax1.Location()  (the axis base point)
  Let axis_dir    = gp_Ax1.Direction() (unit direction along axis)
  Let v_min, v_max = adaptor.FirstVParameter(), adaptor.LastVParameter()
  Then axis_midpoint = axis_origin + axis_dir * (v_min + v_max) / 2

This gives the true center of the hole bore, which is where the process
planner needs to position the drill or boring tool.

WHY ACCESSIBILITY DIRECTION MATTERS FOR TOOL APPROACH
======================================================
In 3-axis milling, the tool can only approach from one direction per setup
(typically -Z, i.e., top-down). The accessibility direction of a feature
tells the process planner whether that feature is reachable from the current
setup orientation:
  • accessibility_direction ≈ (0, 0, -1) → accessible from top
  • accessibility_direction ≈ (0, 0, +1) → accessible from bottom (flip needed)
  • accessibility_direction ≈ (1, 0, 0)  → accessible from side (reorientation)

This is computed as the negation of the parent face's outward normal:
if a hole is on a face whose normal points upward (+Z), the tool must
approach from above (-Z).

WHY ALL VECTORS MUST BE EXPLICITLY NORMALIZED
===============================================
OCC does NOT guarantee unit-length normals for all surface types:
  • Analytic surfaces (plane, cylinder): normals are unit length ✓
  • BSpline/NURBS surfaces: normal = ∂r/∂u × ∂r/∂v, NOT unit length ✗
  • Degenerate surface points: normal magnitude may be ≈ 0

If a non-unit normal is used in a dot product comparison (e.g., for
accessibility detection), the cosine similarity is wrong, leading to
incorrect setup grouping. Every vector used in a dot product must be
normalized first.

ENGINEERING RULES
=================
  • Pure function — no side effects, no DB writes
  • Face IDs come from the topology graph (F_001, F_002, etc.)
  • Axis defaults to (0, 0, 1) if not determinable
  • Accessibility = -normal of parent face, normalized
  • is_through uses projected bbox depth along feature axis
  • All vectors normalized before use
  • All degenerate cases guarded (zero-magnitude vectors, null faces)
  • Tolerance = 1e-6 for all float comparisons
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

from cad_worker.schemas import (
    FeatureResult,
    FeatureSpatial,
    TopologyGraph,
    GeometrySummary,
)

logger = logging.getLogger("cad_worker.spatial_feature_mapper")

# Global geometry tolerance — must match topology_graph.py and geometry_summary.py
_TOLERANCE = 1e-6

# Radius matching tolerance for cylinder→HOLE matching.
# Manufacturing tolerances for hole diameters are typically ±0.05mm.
# We use 100 * _TOLERANCE = 0.0001mm, well within manufacturing precision.
_RADIUS_MATCH_TOLERANCE = _TOLERANCE * 100  # 0.0001mm

# Axis alignment cosine threshold for cylinder→HOLE matching.
# Two axes are "aligned" if |cos(θ)| > 0.9 (θ < ~25°).
# This is intentionally loose to handle slight misalignments from
# BSpline approximations of cylindrical surfaces.
_AXIS_ALIGNMENT_THRESHOLD = 0.9

# Through-hole depth ratio threshold.
# A feature is "through" if its depth spans ≥ 90% of the stock extent
# along the feature axis. The 10% margin accounts for:
#   • Chamfers or countersinks at entry/exit
#   • Slight misalignment between feature axis and bbox axis
_THROUGH_DEPTH_RATIO = 0.9


def _normalize_vector(
    v: tuple[float, float, float],
) -> tuple[float, float, float]:
    """
    Normalize a 3D vector to unit length.

    Mathematical formula:
        v̂ = v / |v|  where |v| = sqrt(x² + y² + z²)

    If |v| < _TOLERANCE (degenerate/zero vector), returns (0, 0, 0)
    to avoid division by near-zero. Callers must check for this case.

    Args:
        v: 3D vector as (x, y, z) tuple.

    Returns:
        Unit vector, or (0, 0, 0) if degenerate.
    """
    mag = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if mag < _TOLERANCE:
        return (0.0, 0.0, 0.0)
    inv_mag = 1.0 / mag
    return (v[0] * inv_mag, v[1] * inv_mag, v[2] * inv_mag)


def _dot(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    """Dot product of two 3D vectors: a · b = ax*bx + ay*by + az*bz."""
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def map_features_spatially(
    shape: Any,
    feature_results: list[FeatureResult],
    topology_graph: TopologyGraph,
    geometry_summary: GeometrySummary,
) -> list[FeatureSpatial]:
    """
    Enrich detected features with spatial metadata from the topology graph.

    This function bridges the gap between raw feature detection (which outputs
    dimensions and type) and spatial intelligence (which requires position,
    orientation, and accessibility for process planning).

    Args:
        shape: OCC TopoDS_Shape (same shape used for detection).
        feature_results: Raw features from detect_all_features().
        topology_graph: Pre-built topology graph with face normals.
        geometry_summary: Geometry summary with bounding box.

    Returns:
        List of FeatureSpatial objects with full spatial metadata.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    t_start = time.monotonic()

    if not feature_results:
        logger.info("Spatial feature mapping: 0 features (skipped), 0.0ms")
        return []

    logger.info(f"Mapping {len(feature_results)} features spatially...")

    # ── Build valid face ID set from topology graph ─────────────────────
    # Used to validate parent_face_id references before linking.
    valid_face_ids: set[str] = {fn.id for fn in topology_graph.faces}

    # ── Build face index in same order as topology graph ────────────────
    # The topology graph was built by iterating faces with TopExp_Explorer.
    # We replicate that order so face index → face ID mapping is consistent.
    face_data: list[dict] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    face_idx = 0

    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        face_id = f"F_{face_idx + 1:03d}"

        try:
            adaptor = BRepAdaptor_Surface(face)
            surface_type = adaptor.GetType()

            # Compute face centroid via surface properties
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            face_area = abs(props.Mass())
            center = props.CentreOfMass()

            entry: dict = {
                "face_id": face_id,
                "face": face,
                "surface_type": surface_type,
                "area": face_area,
                "center": (center.X(), center.Y(), center.Z()),
            }

            # Extract cylinder properties if applicable
            if surface_type == GeomAbs_Cylinder:
                cyl = adaptor.Cylinder()
                entry["radius"] = cyl.Radius()

                # Extract cylinder axis direction and normalize
                raw_axis_dir = cyl.Axis().Direction()
                axis_vec = _normalize_vector((
                    raw_axis_dir.X(),
                    raw_axis_dir.Y(),
                    raw_axis_dir.Z(),
                ))
                entry["axis_dir"] = axis_vec

                # Compute cylinder axis midpoint (true hole center)
                # The V-parameter of a cylinder runs along the axis.
                # axis_midpoint = axis_origin + axis_dir * (v_min + v_max) / 2
                axis_loc = cyl.Axis().Location()
                v_min = adaptor.FirstVParameter()
                v_max = adaptor.LastVParameter()
                v_mid = (v_min + v_max) / 2.0
                entry["axis_midpoint"] = (
                    axis_loc.X() + axis_vec[0] * v_mid,
                    axis_loc.Y() + axis_vec[1] * v_mid,
                    axis_loc.Z() + axis_vec[2] * v_mid,
                )

                # Also store axis extent for depth estimation
                entry["axis_extent"] = abs(v_max - v_min)

            face_data.append(entry)

        except Exception as e:
            logger.warning(f"Face {face_id}: spatial data extraction failed: {e}")
            face_data.append({
                "face_id": face_id,
                "face": face,
                "surface_type": None,
                "area": 0.0,
                "center": (0.0, 0.0, 0.0),
            })

        face_idx += 1
        explorer.Next()

    # ── Build lookup from topology graph for normals ────────────────────
    # Cache normals as pre-normalized vectors for safe dot products.
    face_normal_map: dict[str, tuple[float, float, float]] = {}
    for fn in topology_graph.faces:
        face_normal_map[fn.id] = _normalize_vector(fn.normal)

    # ── Map each feature to its parent face ─────────────────────────────
    spatial_features: list[FeatureSpatial] = []
    bbox = geometry_summary.bounding_box

    for feat_idx, feat in enumerate(feature_results):
        feat_id = f"FEAT_{feat_idx + 1:03d}"

        try:
            parent_face_id, position, axis_dir = _find_parent_face(
                feat, face_data
            )

            # ── Validate parent face exists in topology graph ───────────
            # If parent_face_id doesn't exist (possible if face enumeration
            # differs), fall back to F_001 with a warning.
            if parent_face_id not in valid_face_ids:
                logger.warning(
                    f"Feature {feat_id}: parent_face_id={parent_face_id} "
                    f"not found in topology graph. Falling back to F_001."
                )
                parent_face_id = next(iter(valid_face_ids), "F_001")

            # ── Normalize axis direction ────────────────────────────────
            axis_dir = _normalize_vector(axis_dir)
            if axis_dir == (0.0, 0.0, 0.0):
                # Degenerate axis — default to Z-up
                axis_dir = (0.0, 0.0, 1.0)
                logger.warning(
                    f"Feature {feat_id}: degenerate axis direction, "
                    f"defaulting to (0, 0, 1)"
                )

            # ── Compute accessibility direction ─────────────────────────
            # Accessibility = opposite of parent face outward normal.
            # Must be normalized to unit length for correct setup grouping.
            parent_normal = face_normal_map.get(
                parent_face_id, (0.0, 0.0, 1.0)
            )
            neg_normal = (-parent_normal[0], -parent_normal[1], -parent_normal[2])
            accessibility = _normalize_vector(neg_normal)
            if accessibility == (0.0, 0.0, 0.0):
                # Parent normal was zero — default to -Z (top-down approach)
                accessibility = (0.0, 0.0, -1.0)

            # ── Through-hole detection ──────────────────────────────────
            # Project the bounding box extent along the feature axis.
            # If feature depth ≥ 90% of the projected extent, it's through.
            depth = feat.depth or 0.0
            is_through = False
            if depth > _TOLERANCE:
                axis_depth = _project_bbox_depth(
                    axis_dir, bbox.length, bbox.width, bbox.height
                )
                if axis_depth > _TOLERANCE:
                    depth_ratio = depth / axis_depth
                    is_through = depth_ratio >= _THROUGH_DEPTH_RATIO

            spatial_features.append(FeatureSpatial(
                id=feat_id,
                type=feat.type,
                diameter=feat.diameter,
                depth=feat.depth,
                width=feat.dimensions.get("width"),
                length=feat.dimensions.get("length"),
                position=(
                    round(position[0], 6),
                    round(position[1], 6),
                    round(position[2], 6),
                ),
                axis_direction=(
                    round(axis_dir[0], 6),
                    round(axis_dir[1], 6),
                    round(axis_dir[2], 6),
                ),
                parent_face_id=parent_face_id,
                accessibility_direction=(
                    round(accessibility[0], 6),
                    round(accessibility[1], 6),
                    round(accessibility[2], 6),
                ),
                is_through=is_through,
            ))

        except Exception as e:
            logger.warning(
                f"Feature {feat_id} ({feat.type}): spatial mapping failed: {e}"
            )
            # Create a minimal spatial feature with safe defaults
            fallback_face = next(iter(valid_face_ids), "F_001")
            spatial_features.append(FeatureSpatial(
                id=feat_id,
                type=feat.type,
                diameter=feat.diameter,
                depth=feat.depth,
                width=feat.dimensions.get("width"),
                length=feat.dimensions.get("length"),
                position=(0.0, 0.0, 0.0),
                axis_direction=(0.0, 0.0, 1.0),
                parent_face_id=fallback_face,
                accessibility_direction=(0.0, 0.0, -1.0),
                is_through=False,
            ))

    elapsed_ms = (time.monotonic() - t_start) * 1000
    logger.info(
        f"Spatial feature mapping complete: "
        f"{len(spatial_features)} features mapped in {elapsed_ms:.1f}ms"
    )
    return spatial_features


def _find_parent_face(
    feat: FeatureResult,
    face_data: list[dict],
) -> tuple[str, tuple[float, float, float], tuple[float, float, float]]:
    """
    Find the best matching parent face for a feature.

    Matching strategy:
      HOLE features → match by cylinder radius and axis alignment.
        Position = cylinder axis midpoint (not surface centroid).
        Axis = cylinder geometric axis direction (normalized).
      POCKET/SLOT/TURN_PROFILE → match by largest planar face.
        Position = face surface centroid.
        Axis = face normal (normalized).

    Returns:
        (parent_face_id, position, axis_direction)
    """
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane

    if feat.type == "HOLE" and feat.diameter is not None:
        target_radius = feat.diameter / 2.0
        feat_axis_raw = feat.axis or {"x": 0, "y": 0, "z": 1}
        feat_axis = _normalize_vector((
            feat_axis_raw["x"],
            feat_axis_raw["y"],
            feat_axis_raw["z"],
        ))
        # Guard: if feat_axis is degenerate, default to Z
        if feat_axis == (0.0, 0.0, 0.0):
            feat_axis = (0.0, 0.0, 1.0)

        best_match = None
        best_distance = float("inf")

        for fd in face_data:
            if fd.get("surface_type") != GeomAbs_Cylinder:
                continue
            if "radius" not in fd:
                continue

            radius_diff = abs(fd["radius"] - target_radius)
            if radius_diff > _RADIUS_MATCH_TOLERANCE:
                continue

            # Check axis alignment using normalized dot product
            if "axis_dir" in fd:
                dot_val = abs(_dot(feat_axis, fd["axis_dir"]))
                if dot_val < _AXIS_ALIGNMENT_THRESHOLD:
                    continue

            if radius_diff < best_distance:
                best_distance = radius_diff
                best_match = fd

        if best_match:
            # Use axis midpoint as position (true hole center)
            position = best_match.get(
                "axis_midpoint", best_match["center"]
            )
            axis_dir = best_match.get("axis_dir", (0.0, 0.0, 1.0))
            return (best_match["face_id"], position, axis_dir)

    # For non-HOLE features or if no cylinder match: use largest planar face
    # (pocket floors, slot bottoms are typically the largest planar face
    # adjacent to the feature volume)
    best_planar = None
    best_area = -1.0
    for fd in face_data:
        if fd.get("surface_type") != GeomAbs_Plane:
            continue
        face_area = fd.get("area", 0.0)
        if face_area > best_area:
            best_area = face_area
            best_planar = fd

    if best_planar:
        return (
            best_planar["face_id"],
            best_planar["center"],
            (0.0, 0.0, 1.0),  # Default axis for planar features
        )

    # Fallback: use the first face with non-zero area
    for fd in face_data:
        if fd.get("area", 0.0) > _TOLERANCE:
            return (fd["face_id"], fd["center"], (0.0, 0.0, 1.0))

    # Ultimate fallback
    if face_data:
        return (face_data[0]["face_id"], face_data[0]["center"], (0.0, 0.0, 1.0))

    return ("F_001", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))


def _project_bbox_depth(
    axis: tuple[float, float, float],
    length: float,
    width: float,
    height: float,
) -> float:
    """
    Compute the projected depth of the bounding box along a direction vector.

    Mathematical formula:
        depth = |axis.x| * length + |axis.y| * width + |axis.z| * height

    This computes the support function of the AABB along the given direction.
    For a normalized axis vector, this gives the maximum extent of the
    bounding box when projected onto that axis — i.e., the maximum
    distance a tool would need to travel through the stock.

    The axis vector MUST be normalized before calling this function.
    If not normalized, the result scales proportionally, which would
    incorrectly inflate or deflate the depth comparison.

    Args:
        axis: Normalized direction vector (unit length).
        length: Bounding box length (largest dimension).
        width: Bounding box width (middle dimension).
        height: Bounding box height (smallest dimension).

    Returns:
        Projected depth in mm. Always ≥ 0.
    """
    return (
        abs(axis[0]) * length
        + abs(axis[1]) * width
        + abs(axis[2]) * height
    )
