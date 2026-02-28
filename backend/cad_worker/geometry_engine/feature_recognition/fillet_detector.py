"""
Fillet Detector — identifies internal fillet radii in BRep shapes.

Detection algorithm:
  1. Find CYLINDRICAL faces with small radius (< configurable threshold)
  2. For each candidate, check if it has exactly 2 adjacent PLANAR faces
  3. Verify the planar faces are at a significant angle (> 60°)
  4. Fillet radius = cylinder radius

WHY FILLET DETECTION MATTERS FOR PHASE B
=========================================
  • Fillets are finishing operations — they must be machined AFTER
    the adjacent surfaces are roughed
  • Fillet radius constrains minimum tool radius (ball-end mill)
  • Very small fillets (< 1mm) require micro-tooling
  • Internal fillets at pocket corners are common DFM concerns

WHAT WE DETECT
==============
Internal fillets only — small-radius cylindrical faces between two
intersecting planar surfaces. External blends / rounds use the same
geometry but are typically not machined (they exist in the cast/forged
stock). Full blend classification is Phase C scope.

Deterministic only. No AI.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from cad_worker.geometry_engine.feature_recognition.base import FeatureDetectorBase
from cad_worker.schemas import FeatureResult

logger = logging.getLogger("cad_worker.fillet_detector")

# ── Constants ────────────────────────────────────────────────────────────────

_TOLERANCE = 1e-6

# Maximum fillet radius to detect (mm).
# Larger cylindrical faces are structural, not fillets.
_MAX_FILLET_RADIUS = 10.0

# Minimum angle between adjacent planar faces (radians).
# Below this angle, the "fillet" is more likely a surface blend.
_MIN_ADJACENT_ANGLE = math.radians(60)  # 60°


class FilletDetector(FeatureDetectorBase):
    """
    Detects internal fillets (small cylindrical radius blends).

    A fillet is identified when:
      • A cylindrical face has radius < MAX_FILLET_RADIUS
      • It is adjacent to exactly 2 planar faces
      • The planar faces meet at > 60°

    Returns FeatureResult with type="FILLET", confidence=0.80.
    """

    def detect(self, shape: Any) -> list[FeatureResult]:
        """Detect all fillets in the shape."""
        try:
            return self._detect_impl(shape)
        except Exception as e:
            logger.error(f"Fillet detection failed: {e}", exc_info=True)
            return []

    def _detect_impl(self, shape: Any) -> list[FeatureResult]:
        from OCP.TopExp import TopExp_Explorer, TopExp
        from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
        from OCP.TopoDS import TopoDS
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

        # ── Step 1: Collect all faces with type classification ──────────
        all_faces: list[dict] = []
        face_shapes: list[Any] = []

        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            adaptor = BRepAdaptor_Surface(face)
            stype = adaptor.GetType()

            face_info: dict = {
                "face": face,
                "type": stype,
                "adaptor": adaptor,
            }

            if stype == GeomAbs_Cylinder:
                cyl = adaptor.Cylinder()
                face_info["radius"] = cyl.Radius()
                axis = cyl.Axis()
                face_info["axis_dir"] = (
                    axis.Direction().X(),
                    axis.Direction().Y(),
                    axis.Direction().Z(),
                )
                face_info["axis_loc"] = (
                    axis.Location().X(),
                    axis.Location().Y(),
                    axis.Location().Z(),
                )

                # Compute center
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                center = props.CentreOfMass()
                face_info["center"] = (center.X(), center.Y(), center.Z())

            elif stype == GeomAbs_Plane:
                plane = adaptor.Plane()
                ax = plane.Axis()
                face_info["normal"] = (
                    ax.Direction().X(),
                    ax.Direction().Y(),
                    ax.Direction().Z(),
                )

            all_faces.append(face_info)
            face_shapes.append(face)
            explorer.Next()

        # ── Step 2: Build face adjacency ────────────────────────────────
        edge_face_map = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(
            shape, TopAbs_EDGE, TopAbs_FACE, edge_face_map
        )

        adjacency: dict[int, set[int]] = {i: set() for i in range(len(all_faces))}
        for edge_idx in range(1, edge_face_map.Extent() + 1):
            face_list = edge_face_map.FindFromIndex(edge_idx)
            adj_indices: list[int] = []
            for fi_idx in range(1, face_list.Extent() + 1):
                f = face_list.Value(fi_idx)
                for k, fs in enumerate(face_shapes):
                    if fs.IsSame(f):
                        adj_indices.append(k)
                        break
            for a in range(len(adj_indices)):
                for b in range(a + 1, len(adj_indices)):
                    adjacency[adj_indices[a]].add(adj_indices[b])
                    adjacency[adj_indices[b]].add(adj_indices[a])

        # ── Step 3: Find fillet candidates ──────────────────────────────
        features: list[FeatureResult] = []

        for i, fd in enumerate(all_faces):
            if fd["type"] != GeomAbs_Cylinder:
                continue
            radius = fd.get("radius", 0.0)
            if radius > _MAX_FILLET_RADIUS or radius < _TOLERANCE:
                continue

            # Find adjacent PLANAR faces
            planar_neighbors: list[int] = []
            for j in adjacency.get(i, set()):
                if j < len(all_faces) and all_faces[j]["type"] == GeomAbs_Plane:
                    planar_neighbors.append(j)

            # Fillet must sit between exactly 2 planar faces
            if len(planar_neighbors) < 2:
                continue

            # Check the first valid pair of perpendicular planes
            found = False
            for p in range(len(planar_neighbors)):
                if found:
                    break
                for q in range(p + 1, len(planar_neighbors)):
                    n1 = all_faces[planar_neighbors[p]].get("normal")
                    n2 = all_faces[planar_neighbors[q]].get("normal")
                    if n1 is None or n2 is None:
                        continue

                    angle = _angle_between_normals(n1, n2)
                    if angle < _MIN_ADJACENT_ANGLE:
                        continue

                    # Valid fillet
                    axis_dir = fd.get("axis_dir", (0, 0, 1))
                    center = fd.get("center", (0, 0, 0))

                    features.append(FeatureResult(
                        type="FILLET",
                        dimensions={
                            "radius": round(radius, 6),
                        },
                        depth=None,
                        diameter=round(2.0 * radius, 6),
                        axis={
                            "x": round(axis_dir[0], 6),
                            "y": round(axis_dir[1], 6),
                            "z": round(axis_dir[2], 6),
                        },
                        confidence=0.80,
                    ))
                    found = True
                    break

        logger.info(
            f"Fillet detection: {len(all_faces)} total faces → "
            f"{len(features)} fillets"
        )
        return features


def _angle_between_normals(n1: tuple, n2: tuple) -> float:
    """Compute angle between two normals (handles flipped normals)."""
    dot = n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]
    dot = max(-1.0, min(1.0, dot))
    return math.acos(abs(dot))
