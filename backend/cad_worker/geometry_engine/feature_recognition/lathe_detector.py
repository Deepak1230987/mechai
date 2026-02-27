"""
Lathe Profile Detector — identifies parts with strong rotational symmetry.

Detection heuristic:
  1. Count face types: cylindrical, conical, spherical, planar, other
  2. If majority of faces are surfaces of revolution (cylinder/cone/sphere):
     → likely a turned part
  3. Check axis alignment consistency among cylindrical faces
  4. If dominant axis exists and revolution faces > threshold:
     → flag as TURN_PROFILE

This is a heuristic indicator, not a full profile recognition.
Confidence is 0.7 (lower than geometric detectors).

Deterministic only. No AI.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from cad_worker.geometry_engine.feature_recognition.base import FeatureDetectorBase
from cad_worker.schemas import FeatureResult

logger = logging.getLogger("cad_worker.lathe_detector")

_TOLERANCE = 1e-4
# Threshold: fraction of faces that must be surfaces of revolution
_REVOLUTION_FACE_THRESHOLD = 0.5
# Threshold: fraction of cylindrical axes that must align
_AXIS_ALIGNMENT_THRESHOLD = 0.6


class LatheDetector(FeatureDetectorBase):
    """
    Detects parts that are primarily turned (lathe) profiles.

    A part is flagged as a turning candidate when:
      • Majority of faces are surfaces of revolution (cylinder, cone, sphere)
      • Cylindrical/conical axes are predominantly aligned to a single axis
      • The part exhibits strong rotational symmetry

    Returns at most one FeatureResult with type="TURN_PROFILE",
    confidence=0.7. Empty list if not a turning part.
    """

    def detect(self, shape: Any) -> list[FeatureResult]:
        """Detect if the shape is a lathe profile."""
        try:
            return self._detect_impl(shape)
        except Exception as e:
            logger.error(f"Lathe detection failed: {e}", exc_info=True)
            return []

    def _detect_impl(self, shape: Any) -> list[FeatureResult]:
        from OCP.GeomAbs import (
            GeomAbs_Plane,
            GeomAbs_Cylinder,
            GeomAbs_Cone,
            GeomAbs_Sphere,
            GeomAbs_Torus,
        )
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        from cad_worker.geometry_engine.feature_recognition.face_iterator import iter_faces

        # ── Step 1: Classify all faces ───────────────────────────────────
        total_faces = 0
        planar_count = 0
        cylinder_count = 0
        cone_count = 0
        sphere_count = 0
        torus_count = 0
        other_count = 0

        # Collect cylinder/cone axes for alignment check
        axes: list[tuple[float, float, float]] = []

        for fi in iter_faces(shape):
            total_faces += 1
            stype = fi.effective_type

            if stype == GeomAbs_Plane:
                planar_count += 1
            elif stype == GeomAbs_Cylinder:
                cylinder_count += 1
                if fi.bspline_axis is not None:
                    axes.append((
                        fi.bspline_axis["x"],
                        fi.bspline_axis["y"],
                        fi.bspline_axis["z"],
                    ))
                else:
                    cyl = fi.adaptor.Cylinder()
                    d = cyl.Axis().Direction()
                    axes.append((d.X(), d.Y(), d.Z()))
            elif stype == GeomAbs_Cone:
                cone_count += 1
                if fi.bspline_axis is not None:
                    axes.append((
                        fi.bspline_axis["x"],
                        fi.bspline_axis["y"],
                        fi.bspline_axis["z"],
                    ))
                else:
                    cone = fi.adaptor.Cone()
                    d = cone.Axis().Direction()
                    axes.append((d.X(), d.Y(), d.Z()))
            elif stype == GeomAbs_Sphere:
                sphere_count += 1
            elif stype == GeomAbs_Torus:
                torus_count += 1
            else:
                other_count += 1

        if total_faces == 0:
            return []

        # ── Step 2: Check revolution face ratio ──────────────────────────
        revolution_faces = cylinder_count + cone_count + sphere_count + torus_count
        revolution_ratio = revolution_faces / total_faces

        logger.debug(
            f"Lathe check: total={total_faces}, "
            f"rev={revolution_faces} ({revolution_ratio:.2f}), "
            f"cyl={cylinder_count}, cone={cone_count}, "
            f"sphere={sphere_count}, torus={torus_count}, "
            f"planar={planar_count}, other={other_count}"
        )

        if revolution_ratio < _REVOLUTION_FACE_THRESHOLD:
            logger.info(
                f"Lathe detection: revolution ratio {revolution_ratio:.2f} "
                f"below threshold {_REVOLUTION_FACE_THRESHOLD} — not a lathe part"
            )
            return []

        # ── Step 3: Check axis alignment consistency ─────────────────────
        dominant_axis, alignment_ratio = self._find_dominant_axis(axes)

        if dominant_axis is None or alignment_ratio < _AXIS_ALIGNMENT_THRESHOLD:
            logger.info(
                f"Lathe detection: axis alignment {alignment_ratio:.2f} "
                f"below threshold — not a lathe part"
            )
            return []

        # ── Step 4: Get bounding box for dimensions ──────────────────────
        part_bbox = Bnd_Box()
        BRepBndLib.Add_s(shape, part_bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = part_bbox.Get()

        bbox_dict = {
            "xmin": round(xmin, 6), "ymin": round(ymin, 6), "zmin": round(zmin, 6),
            "xmax": round(xmax, 6), "ymax": round(ymax, 6), "zmax": round(zmax, 6),
            "x_size": round(xmax - xmin, 6),
            "y_size": round(ymax - ymin, 6),
            "z_size": round(zmax - zmin, 6),
        }

        axis_dict = {
            "x": round(dominant_axis[0], 6),
            "y": round(dominant_axis[1], 6),
            "z": round(dominant_axis[2], 6),
        }

        logger.info(
            f"Lathe detection: TURN_PROFILE detected — "
            f"rev_ratio={revolution_ratio:.2f}, "
            f"axis_alignment={alignment_ratio:.2f}, "
            f"dominant_axis={axis_dict}"
        )

        return [
            FeatureResult(
                type="TURN_PROFILE",
                dimensions={
                    "bounding_box": bbox_dict,
                    "revolution_face_ratio": round(revolution_ratio, 4),
                    "axis_alignment_ratio": round(alignment_ratio, 4),
                    "cylinder_faces": cylinder_count,
                    "cone_faces": cone_count,
                    "sphere_faces": sphere_count,
                },
                axis=axis_dict,
                confidence=0.7,
            )
        ]

    @staticmethod
    def _find_dominant_axis(
        axes: list[tuple[float, float, float]],
    ) -> tuple[tuple[float, float, float] | None, float]:
        """
        Find the dominant axis direction among collected cylinder/cone axes.

        Returns (dominant_axis, alignment_ratio) where alignment_ratio
        is the fraction of axes parallel to the dominant one.
        """
        if not axes:
            return None, 0.0

        if len(axes) == 1:
            return axes[0], 1.0

        # Try each axis as the candidate dominant direction
        best_axis: tuple[float, float, float] | None = None
        best_count = 0

        for candidate in axes:
            aligned = 0
            cn = math.sqrt(
                candidate[0] ** 2 + candidate[1] ** 2 + candidate[2] ** 2
            )
            if cn < _TOLERANCE:
                continue

            for other in axes:
                on = math.sqrt(other[0] ** 2 + other[1] ** 2 + other[2] ** 2)
                if on < _TOLERANCE:
                    continue

                dot = (
                    candidate[0] * other[0]
                    + candidate[1] * other[1]
                    + candidate[2] * other[2]
                ) / (cn * on)

                # Parallel or anti-parallel
                if abs(abs(dot) - 1.0) < 0.05:
                    aligned += 1

            if aligned > best_count:
                best_count = aligned
                best_axis = candidate

        ratio = best_count / len(axes) if axes else 0.0
        return best_axis, ratio
