"""
Chamfer Detector — identifies chamfered edges in BRep shapes.

Detection algorithm:
  1. Find PLANAR faces with small area (< 5% of max face area)
  2. For each small face, check if it has exactly 2 adjacent planar faces
  3. Verify the adjacent faces are roughly perpendicular (70°–110°)
  4. Verify the candidate face normal is at ~45° to both adjacents (35°–55°)
  5. Compute chamfer width from shortest edge length

WHY CHAMFER DETECTION MATTERS FOR PHASE B
==========================================
  • Each chamfer is a distinct machining operation after the parent edge
  • Chamfer width determines tool selection (chamfer mill diameter)
  • Small chamfers (< 0.5mm) need micro-tooling → cost/risk flag
  • Chamfers on holes need sequencing after drilling

Deterministic only. No AI.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from cad_worker.geometry_engine.feature_recognition.base import FeatureDetectorBase
from cad_worker.schemas import FeatureResult

logger = logging.getLogger("cad_worker.chamfer_detector")

# ── Constants ────────────────────────────────────────────────────────────────

_TOLERANCE = 1e-6

# Maximum face area as fraction of largest face to be considered a chamfer.
# Chamfers are always small relative to the part.
_MAX_AREA_FRACTION = 0.05

# Angle between adjacent faces must be roughly perpendicular (90° ± 20°)
_PERPENDICULAR_MIN = math.radians(70)  # 70°
_PERPENDICULAR_MAX = math.radians(110)  # 110°

# Chamfer face normal must be at ~45° to the adjacent faces (45° ± 10°)
_CHAMFER_ANGLE_MIN = math.radians(35)  # 35°
_CHAMFER_ANGLE_MAX = math.radians(55)  # 55°


class ChamferDetector(FeatureDetectorBase):
    """
    Detects chamfered edges in a BRep shape.

    A chamfer is identified when:
      • A small planar face exists between two larger planar faces
      • The two larger faces are roughly perpendicular
      • The chamfer face normal is at ~45° to both larger faces

    Returns FeatureResult with type="CHAMFER", confidence=0.85.
    """

    def detect(self, shape: Any) -> list[FeatureResult]:
        """Detect all chamfers in the shape."""
        try:
            return self._detect_impl(shape)
        except Exception as e:
            logger.error(f"Chamfer detection failed: {e}", exc_info=True)
            return []

    def _detect_impl(self, shape: Any) -> list[FeatureResult]:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
        from OCP.TopoDS import TopoDS
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.GeomAbs import GeomAbs_Plane
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GCPnts import GCPnts_AbscissaPoint
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
        from OCP.TopExp import TopExp

        # ── Step 1: Collect all planar faces with area and normal ────────
        face_data: list[dict] = []
        face_shapes: list[Any] = []

        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            adaptor = BRepAdaptor_Surface(face)

            if adaptor.GetType() == GeomAbs_Plane:
                # Compute area
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                area = props.Mass()

                # Get normal
                plane = adaptor.Plane()
                ax = plane.Axis()
                normal_dir = ax.Direction()

                # Get center
                center = props.CentreOfMass()

                face_data.append({
                    "face": face,
                    "area": area,
                    "normal": (normal_dir.X(), normal_dir.Y(), normal_dir.Z()),
                    "center": (center.X(), center.Y(), center.Z()),
                })
                face_shapes.append(face)

            explorer.Next()

        if len(face_data) < 3:
            logger.info("Chamfer detection: not enough planar faces")
            return []

        # ── Step 2: Build face adjacency map ────────────────────────────
        edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map)

        adjacency: dict[int, set[int]] = {i: set() for i in range(len(face_data))}
        for edge_idx in range(1, edge_face_map.Extent() + 1):
            face_list = edge_face_map.FindFromIndex(edge_idx)
            adjacent_indices: list[int] = []
            for fi_idx in range(1, face_list.Extent() + 1):
                f = face_list.Value(fi_idx)
                for k, fs in enumerate(face_shapes):
                    if fs.IsSame(f):
                        adjacent_indices.append(k)
                        break
            # Mark pairwise adjacency
            for a in range(len(adjacent_indices)):
                for b in range(a + 1, len(adjacent_indices)):
                    adjacency[adjacent_indices[a]].add(adjacent_indices[b])
                    adjacency[adjacent_indices[b]].add(adjacent_indices[a])

        # ── Step 3: Find max area for threshold ─────────────────────────
        max_area = max(fd["area"] for fd in face_data)
        area_threshold = max_area * _MAX_AREA_FRACTION

        # ── Step 4: Identify chamfer candidates ─────────────────────────
        features: list[FeatureResult] = []

        for i, fd in enumerate(face_data):
            if fd["area"] > area_threshold:
                continue  # Too large to be a chamfer

            # Find adjacent planar faces
            adj_planar: list[int] = []
            for j in adjacency.get(i, set()):
                if j < len(face_data):
                    adj_planar.append(j)

            if len(adj_planar) < 2:
                continue  # Need at least 2 adjacent faces

            # Try all pairs of adjacent faces
            for p in range(len(adj_planar)):
                for q in range(p + 1, len(adj_planar)):
                    j1 = adj_planar[p]
                    j2 = adj_planar[q]

                    n_chamfer = fd["normal"]
                    n1 = face_data[j1]["normal"]
                    n2 = face_data[j2]["normal"]

                    # Check adjacent faces are roughly perpendicular
                    angle_12 = _angle_between(n1, n2)
                    if not (_PERPENDICULAR_MIN <= angle_12 <= _PERPENDICULAR_MAX):
                        continue

                    # Check chamfer face is at ~45° to both
                    angle_c1 = _angle_between(n_chamfer, n1)
                    angle_c2 = _angle_between(n_chamfer, n2)

                    if not (_CHAMFER_ANGLE_MIN <= angle_c1 <= _CHAMFER_ANGLE_MAX):
                        continue
                    if not (_CHAMFER_ANGLE_MIN <= angle_c2 <= _CHAMFER_ANGLE_MAX):
                        continue

                    # ── Compute chamfer width (shortest edge) ───────────
                    chamfer_width = _compute_chamfer_width(fd["face"])

                    features.append(FeatureResult(
                        type="CHAMFER",
                        dimensions={
                            "width": round(chamfer_width, 6),
                            "area": round(fd["area"], 6),
                        },
                        depth=None,
                        diameter=None,
                        axis={
                            "x": round(n_chamfer[0], 6),
                            "y": round(n_chamfer[1], 6),
                            "z": round(n_chamfer[2], 6),
                        },
                        confidence=0.85,
                    ))
                    break  # Found a valid chamfer pair, don't duplicate
                else:
                    continue
                break  # Break outer loop too

        logger.info(
            f"Chamfer detection: {len(face_data)} planar faces → "
            f"{len(features)} chamfers"
        )
        return features


def _angle_between(n1: tuple, n2: tuple) -> float:
    """
    Compute angle between two normal vectors in radians.

    Uses: angle = acos(|dot(n1, n2)|)
    The absolute value handles flipped normals.
    """
    dot = n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]
    # Clamp to [-1, 1] for numerical safety
    dot = max(-1.0, min(1.0, dot))
    return math.acos(abs(dot))


def _compute_chamfer_width(face: Any) -> float:
    """
    Compute chamfer width as the shortest edge length on the face.

    The chamfer width is the cross-sectional dimension, which corresponds
    to the shortest boundary edge of the chamfer planar face.
    """
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_AbscissaPoint

    min_length = float("inf")
    edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)

    while edge_explorer.More():
        edge = TopoDS.Edge_s(edge_explorer.Current())
        try:
            curve = BRepAdaptor_Curve(edge)
            length = GCPnts_AbscissaPoint.Length_s(curve)
            if length > 0 and length < min_length:
                min_length = length
        except Exception:
            pass
        edge_explorer.Next()

    return min_length if min_length != float("inf") else 0.0
