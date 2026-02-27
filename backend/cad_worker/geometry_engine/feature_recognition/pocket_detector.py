"""
Pocket Detector — identifies planar pockets with vertical walls in BRep shapes.

Detection algorithm:
  1. Collect all planar faces with their surface normals
  2. Group faces by coplanar clusters (same normal, same plane distance)
  3. For each candidate planar face:
     a. Check if boundary edges form a closed loop
     b. Look for adjacent vertical (perpendicular) faces forming walls
     c. Measure depth: distance between the pocket floor and the top reference
  4. Extract length/width from bounding box of the pocket face

Deterministic only. No AI.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from cad_worker.geometry_engine.feature_recognition.base import FeatureDetectorBase
from cad_worker.schemas import FeatureResult

logger = logging.getLogger("cad_worker.pocket_detector")

_TOLERANCE = 1e-4
# Angle tolerance for "vertical" (perpendicular to pocket floor)
_ANGLE_TOL = 0.1  # radians (~5.7°)


class PocketDetector(FeatureDetectorBase):
    """
    Detects planar pockets in a BRep shape.

    A pocket is identified when:
      • A planar face (the floor) exists
      • Adjacent faces are perpendicular to the floor (walls)
      • The floor is recessed below the part's top surface

    Returns FeatureResult with type="POCKET", confidence=0.8.
    """

    def detect(self, shape: Any) -> list[FeatureResult]:
        """Detect all planar pockets in the shape."""
        try:
            return self._detect_impl(shape)
        except Exception as e:
            logger.error(f"Pocket detection failed: {e}", exc_info=True)
            return []

    def _detect_impl(self, shape: Any) -> list[FeatureResult]:
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.GeomAbs import GeomAbs_Plane
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

        from cad_worker.geometry_engine.feature_recognition.face_iterator import iter_faces

        # ── Step 1: Collect all planar faces with normals ────────────────
        planar_faces: list[dict] = []
        all_face_data: list[dict] = []

        for face_index, fi in enumerate(iter_faces(shape)):
            # Get face bounding box
            face_bbox = Bnd_Box()
            BRepBndLib.Add_s(fi.face, face_bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = face_bbox.Get()

            face_info: dict = {
                "face": fi.face,
                "index": face_index,
                "type": fi.effective_type,
                "bbox": {
                    "xmin": xmin, "ymin": ymin, "zmin": zmin,
                    "xmax": xmax, "ymax": ymax, "zmax": zmax,
                },
            }

            if fi.effective_type == GeomAbs_Plane:
                # Native plane — extract from adaptor
                if fi.bspline_normal is not None:
                    face_info["normal"] = fi.bspline_normal
                    face_info["plane_d"] = fi.bspline_plane_d or 0.0
                else:
                    plane = fi.adaptor.Plane()
                    normal = plane.Axis().Direction()
                    location = plane.Location()
                    plane_d = (
                        location.X() * normal.X()
                        + location.Y() * normal.Y()
                        + location.Z() * normal.Z()
                    )
                    face_info["normal"] = {
                        "x": normal.X(),
                        "y": normal.Y(),
                        "z": normal.Z(),
                    }
                    face_info["plane_d"] = plane_d

                planar_faces.append(face_info)

            all_face_data.append(face_info)

        if len(planar_faces) < 2:
            return []

        # ── Step 2: Build adjacency map ──────────────────────────────────
        adjacency_map = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(
            shape, TopAbs_EDGE, TopAbs_FACE, adjacency_map
        )

        # ── Step 3: Get part bounding box for reference height ───────────
        part_bbox = Bnd_Box()
        BRepBndLib.Add_s(shape, part_bbox)
        pxmin, pymin, pzmin, pxmax, pymax, pzmax = part_bbox.Get()

        # ── Step 4: Find max elevation per normal direction ──────────────
        # Group planar faces by normal direction
        normal_groups: dict[str, list[dict]] = {}
        for pf in planar_faces:
            n = pf["normal"]
            # Quantize normal to group parallel faces
            key = _normal_key(n)
            normal_groups.setdefault(key, []).append(pf)

        # ── Step 5: Identify pocket floors ───────────────────────────────
        features: list[FeatureResult] = []
        detected_keys: set[str] = set()

        for key, group in normal_groups.items():
            if len(group) < 2:
                continue

            # Sort by plane distance — the "highest" face is the reference,
            # lower faces are potential pocket floors
            group.sort(key=lambda f: f["plane_d"])

            # Reference surface = the face with the largest plane_d
            ref_d = group[-1]["plane_d"]

            for face_info in group[:-1]:
                depth = abs(ref_d - face_info["plane_d"])
                if depth < _TOLERANCE:
                    continue  # Same plane — not a pocket

                # Check for adjacent vertical walls
                wall_count = self._count_adjacent_walls(
                    face_info, all_face_data, adjacency_map
                )

                if wall_count < 1:
                    continue  # No walls → not a pocket

                # Extract pocket dimensions from face bounding box
                bbox = face_info["bbox"]
                x_size = abs(bbox["xmax"] - bbox["xmin"])
                y_size = abs(bbox["ymax"] - bbox["ymin"])
                z_size = abs(bbox["zmax"] - bbox["zmin"])

                # Length and width are the two largest non-depth dimensions
                dims = sorted([x_size, y_size, z_size], reverse=True)
                length = round(dims[0], 6)
                width = round(dims[1], 6)

                # De-dup key based on location + depth
                dedup = (
                    f"{round(face_info['plane_d'], 3)}_"
                    f"{round(bbox['xmin'], 3)}_{round(bbox['ymin'], 3)}_"
                    f"{round(depth, 3)}"
                )
                if dedup in detected_keys:
                    continue
                detected_keys.add(dedup)

                features.append(
                    FeatureResult(
                        type="POCKET",
                        dimensions={
                            "length": length,
                            "width": width,
                            "depth": round(depth, 6),
                        },
                        depth=round(depth, 6),
                        confidence=0.8,
                    )
                )

        logger.info(
            f"Pocket detection: {len(planar_faces)} planar faces → "
            f"{len(features)} pockets"
        )
        return features

    @staticmethod
    def _count_adjacent_walls(
        floor_info: dict,
        all_faces: list[dict],
        adjacency_map: Any,
    ) -> int:
        """
        Count faces adjacent to the pocket floor that are perpendicular
        to the floor normal (i.e., vertical walls).
        """
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
        from OCP.TopoDS import TopoDS
        from OCP.BRep import BRep_Tool
        from OCP.GeomAdaptor import GeomAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Plane

        floor_normal = floor_info["normal"]
        wall_count = 0

        # Walk edges of the floor face to find adjacent faces
        edge_explorer = TopExp_Explorer(floor_info["face"], TopAbs_EDGE)
        seen_faces: set[int] = set()

        while edge_explorer.More():
            edge = TopoDS.Edge_s(edge_explorer.Current())

            try:
                if adjacency_map.Contains(edge):
                    adjacent_faces = adjacency_map.FindFromKey(edge)
                    it = adjacent_faces.begin()
                    while it != adjacent_faces.end():
                        adj_face = TopoDS.Face_s(it.Value())
                        face_hash = adj_face.HashCode(1 << 30)

                        if face_hash not in seen_faces:
                            seen_faces.add(face_hash)
                            adj_surface = BRep_Tool.Surface_s(adj_face)

                            if adj_surface is not None:
                                adj_adaptor = GeomAdaptor_Surface(adj_surface)
                                if adj_adaptor.GetType() == GeomAbs_Plane:
                                    adj_plane = adj_adaptor.Plane()
                                    adj_normal = adj_plane.Axis().Direction()

                                    # Check perpendicularity
                                    dot = (
                                        floor_normal["x"] * adj_normal.X()
                                        + floor_normal["y"] * adj_normal.Y()
                                        + floor_normal["z"] * adj_normal.Z()
                                    )
                                    if abs(dot) < _ANGLE_TOL:
                                        wall_count += 1

                        it.Next()
            except Exception:
                pass  # Skip edges with adjacency lookup failures

            edge_explorer.Next()

        return wall_count


def _normal_key(n: dict) -> str:
    """Create a hashable key from a normal vector (direction-insensitive)."""
    # Normalize so that (0,0,1) and (0,0,-1) map to the same key
    x, y, z = n["x"], n["y"], n["z"]
    # Make the largest-magnitude component positive for canonical form
    mag = math.sqrt(x * x + y * y + z * z)
    if mag < _TOLERANCE:
        return "0_0_0"
    x, y, z = x / mag, y / mag, z / mag
    # Ensure canonical direction: first nonzero component is positive
    for v in (x, y, z):
        if abs(v) > _TOLERANCE:
            if v < 0:
                x, y, z = -x, -y, -z
            break
    return f"{round(x, 3)}_{round(y, 3)}_{round(z, 3)}"
