"""
Slot Detector — identifies parallel-face slots in BRep shapes.

Detection algorithm:
  1. Collect all planar faces with normals
  2. Find pairs of parallel planar faces with opposite normals
  3. Compute the constant separation distance (slot width)
  4. Validate that the pair has consistent depth
  5. Extract slot dimensions from face bounding boxes

Deterministic only. No AI.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from cad_worker.geometry_engine.feature_recognition.base import FeatureDetectorBase
from cad_worker.schemas import FeatureResult

logger = logging.getLogger("cad_worker.slot_detector")

_TOLERANCE = 1e-4
_PARALLEL_DOT_TOL = 0.05  # cos(angle) tolerance for parallel check


class SlotDetector(FeatureDetectorBase):
    """
    Detects slots formed by two parallel planar faces at constant separation.

    A slot is identified when:
      • Two planar faces have anti-parallel normals (facing each other)
      • The separation (slot width) is constant and reasonable
      • The faces have overlapping extent (they actually bound a channel)

    Returns FeatureResult with type="SLOT", confidence=0.75.
    """

    def detect(self, shape: Any) -> list[FeatureResult]:
        """Detect all slots in the shape."""
        try:
            return self._detect_impl(shape)
        except Exception as e:
            logger.error(f"Slot detection failed: {e}", exc_info=True)
            return []

    def _detect_impl(self, shape: Any) -> list[FeatureResult]:
        from OCP.GeomAbs import GeomAbs_Plane
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        from cad_worker.geometry_engine.feature_recognition.face_iterator import iter_faces

        # ── Step 1: Collect planar faces ─────────────────────────────────
        planar_faces: list[dict] = []

        for fi in iter_faces(shape):
            if fi.effective_type != GeomAbs_Plane:
                continue

            # Get normal and plane_d
            if fi.bspline_normal is not None:
                normal_tuple = (
                    fi.bspline_normal["x"],
                    fi.bspline_normal["y"],
                    fi.bspline_normal["z"],
                )
                plane_d = fi.bspline_plane_d or 0.0
            else:
                plane = fi.adaptor.Plane()
                normal = plane.Axis().Direction()
                location = plane.Location()
                normal_tuple = (normal.X(), normal.Y(), normal.Z())
                plane_d = (
                    location.X() * normal.X()
                    + location.Y() * normal.Y()
                    + location.Z() * normal.Z()
                )

            face_bbox = Bnd_Box()
            BRepBndLib.Add_s(fi.face, face_bbox)
            bxmin, bymin, bzmin, bxmax, bymax, bzmax = face_bbox.Get()

            planar_faces.append({
                "face": fi.face,
                "normal": normal_tuple,
                "plane_d": plane_d,
                "bbox": {
                    "xmin": bxmin, "ymin": bymin, "zmin": bzmin,
                    "xmax": bxmax, "ymax": bymax, "zmax": bzmax,
                },
            })

        if len(planar_faces) < 2:
            return []

        # ── Step 2: Find anti-parallel pairs ─────────────────────────────
        features: list[FeatureResult] = []
        used_indices: set[int] = set()

        for i in range(len(planar_faces)):
            if i in used_indices:
                continue

            for j in range(i + 1, len(planar_faces)):
                if j in used_indices:
                    continue

                fi = planar_faces[i]
                fj = planar_faces[j]

                # Check anti-parallel normals (facing each other)
                dot = (
                    fi["normal"][0] * fj["normal"][0]
                    + fi["normal"][1] * fj["normal"][1]
                    + fi["normal"][2] * fj["normal"][2]
                )

                if dot > -1.0 + _PARALLEL_DOT_TOL:
                    # Not anti-parallel
                    continue

                # Compute slot width (distance between parallel planes)
                width = abs(fi["plane_d"] - fj["plane_d"])
                if width < _TOLERANCE:
                    continue  # Same plane

                # Check overlapping extent
                if not self._bboxes_overlap(fi["bbox"], fj["bbox"]):
                    continue

                # Get part bounding box for reference
                part_bbox = Bnd_Box()
                BRepBndLib.Add_s(shape, part_bbox)
                _, _, _, pxmax, pymax, pzmax = part_bbox.Get()

                # Compute slot length and depth from overlapping region
                overlap = self._compute_overlap_dims(fi["bbox"], fj["bbox"])
                length = overlap["length"]
                depth = overlap["depth"]

                if length < _TOLERANCE or depth < _TOLERANCE:
                    continue

                # Filter out face pairs that are too large relative to part
                # (likely opposing part walls, not slots)
                part_bbox_data = part_bbox.Get()
                part_max_dim = max(
                    part_bbox_data[3] - part_bbox_data[0],
                    part_bbox_data[4] - part_bbox_data[1],
                    part_bbox_data[5] - part_bbox_data[2],
                )
                if width > part_max_dim * 0.6:
                    continue  # Too wide — probably opposing walls

                used_indices.add(i)
                used_indices.add(j)

                features.append(
                    FeatureResult(
                        type="SLOT",
                        dimensions={
                            "width": round(width, 6),
                            "length": round(length, 6),
                            "depth": round(depth, 6),
                        },
                        depth=round(depth, 6),
                        confidence=0.75,
                    )
                )

        logger.info(
            f"Slot detection: {len(planar_faces)} planar faces → "
            f"{len(features)} slots"
        )
        return features

    @staticmethod
    def _bboxes_overlap(a: dict, b: dict) -> bool:
        """Check if two bounding boxes overlap in at least 2 dimensions."""
        overlap_count = 0
        for dim in ("x", "y", "z"):
            a_min = a[f"{dim}min"]
            a_max = a[f"{dim}max"]
            b_min = b[f"{dim}min"]
            b_max = b[f"{dim}max"]
            if a_min <= b_max + _TOLERANCE and b_min <= a_max + _TOLERANCE:
                overlap_count += 1
        return overlap_count >= 2

    @staticmethod
    def _compute_overlap_dims(a: dict, b: dict) -> dict:
        """
        Compute the overlapping dimensions between two face bounding boxes.
        Returns length (largest overlap) and depth (smallest overlap).
        """
        overlaps = []
        for dim in ("x", "y", "z"):
            a_min = a[f"{dim}min"]
            a_max = a[f"{dim}max"]
            b_min = b[f"{dim}min"]
            b_max = b[f"{dim}max"]

            # Size of each face in this dimension
            a_size = a_max - a_min
            b_size = b_max - b_min
            # Use the average face extent
            avg_size = (a_size + b_size) / 2.0
            overlaps.append(avg_size)

        overlaps.sort(reverse=True)
        return {
            "length": overlaps[0] if len(overlaps) > 0 else 0.0,
            "depth": overlaps[1] if len(overlaps) > 1 else 0.0,
        }
