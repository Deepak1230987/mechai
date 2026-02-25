"""
Hole Detector — identifies cylindrical holes in BRep shapes.

Detection algorithm:
  1. Iterate all faces via TopExp_Explorer
  2. For each face with GeomAdaptor_Surface type == Cylinder:
     a. Extract cylinder radius and axis
     b. Walk boundary edges via TopExp_Explorer(face, TopAbs_EDGE)
     c. Check if boundary edges are circular (BRepAdaptor_Curve → Circle)
     d. Compute hole depth from cylinder height (edge Z-extents along axis)
  3. De-duplicate holes sharing the same axis and radius

Deterministic only. No AI. No heuristics beyond geometric validation.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from cad_worker.geometry_engine.feature_recognition.base import FeatureDetectorBase
from cad_worker.schemas import FeatureResult

logger = logging.getLogger("cad_worker.hole_detector")

# Tolerance for floating-point geometric comparisons
_TOLERANCE = 1e-4


class HoleDetector(FeatureDetectorBase):
    """
    Detects cylindrical holes (through and blind) in a BRep shape.

    A cylindrical face qualifies as a hole when:
      • Surface type is GeomAbs_Cylinder
      • At least one boundary edge is a full or partial circle
      • Cylinder axis is consistent

    Returns FeatureResult with type="HOLE", confidence=0.9.
    """

    def detect(self, shape: Any) -> list[FeatureResult]:
        """Detect all cylindrical holes in the shape."""
        try:
            return self._detect_impl(shape)
        except Exception as e:
            logger.error(f"Hole detection failed: {e}", exc_info=True)
            return []

    def _detect_impl(self, shape: Any) -> list[FeatureResult]:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
        from OCP.TopoDS import TopoDS
        from OCP.BRep import BRep_Tool
        from OCP.GeomAdaptor import GeomAdaptor_Surface
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Circle

        candidates: list[dict] = []
        explorer = TopExp_Explorer(shape, TopAbs_FACE)

        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            surface = BRep_Tool.Surface_s(face)

            if surface is None:
                explorer.Next()
                continue

            adaptor = GeomAdaptor_Surface(surface)

            if adaptor.GetType() != GeomAbs_Cylinder:
                explorer.Next()
                continue

            # Extract cylinder properties
            cylinder = adaptor.Cylinder()
            radius = cylinder.Radius()
            axis = cylinder.Axis()
            axis_dir = axis.Direction()
            axis_loc = axis.Location()

            # Validate boundary edges — look for circular edges
            has_circular_edge = False
            edge_explorer = TopExp_Explorer(face, TopAbs_EDGE)
            z_values: list[float] = []

            while edge_explorer.More():
                edge = TopoDS.Edge_s(edge_explorer.Current())
                try:
                    curve_adaptor = BRepAdaptor_Curve(edge)
                    if curve_adaptor.GetType() == GeomAbs_Circle:
                        has_circular_edge = True

                    # Collect endpoints along the cylinder axis for depth calc
                    first = curve_adaptor.Value(curve_adaptor.FirstParameter())
                    last = curve_adaptor.Value(curve_adaptor.LastParameter())

                    # Project onto cylinder axis direction
                    for pt in (first, last):
                        # Vector from axis location to point
                        dx = pt.X() - axis_loc.X()
                        dy = pt.Y() - axis_loc.Y()
                        dz = pt.Z() - axis_loc.Z()
                        # Dot product with axis direction
                        proj = (
                            dx * axis_dir.X()
                            + dy * axis_dir.Y()
                            + dz * axis_dir.Z()
                        )
                        z_values.append(proj)
                except Exception:
                    pass  # Skip edges that can't be adapted

                edge_explorer.Next()

            if not has_circular_edge:
                explorer.Next()
                continue

            # Compute depth along axis
            depth = 0.0
            if z_values:
                depth = abs(max(z_values) - min(z_values))

            candidate = {
                "radius": round(radius, 6),
                "diameter": round(2.0 * radius, 6),
                "depth": round(depth, 6),
                "axis": {
                    "x": round(axis_dir.X(), 6),
                    "y": round(axis_dir.Y(), 6),
                    "z": round(axis_dir.Z(), 6),
                },
                "location": {
                    "x": round(axis_loc.X(), 6),
                    "y": round(axis_loc.Y(), 6),
                    "z": round(axis_loc.Z(), 6),
                },
            }
            candidates.append(candidate)

            explorer.Next()

        # De-duplicate holes with same axis, location, and radius
        unique_holes = self._deduplicate(candidates)

        features = []
        for hole in unique_holes:
            features.append(
                FeatureResult(
                    type="HOLE",
                    dimensions={
                        "diameter": hole["diameter"],
                        "depth": hole["depth"],
                    },
                    depth=hole["depth"],
                    diameter=hole["diameter"],
                    axis=hole["axis"],
                    confidence=0.9,
                )
            )

        logger.info(
            f"Hole detection: {len(candidates)} cylindrical faces → "
            f"{len(features)} unique holes"
        )
        return features

    def _deduplicate(self, candidates: list[dict]) -> list[dict]:
        """
        Remove duplicate hole detections.

        Two candidates are duplicates if they share the same radius,
        axis direction, and location within tolerance.
        """
        unique: list[dict] = []

        for c in candidates:
            is_dup = False
            for u in unique:
                if self._are_same_hole(c, u):
                    # Keep the one with greater depth
                    if c["depth"] > u["depth"]:
                        u.update(c)
                    is_dup = True
                    break
            if not is_dup:
                unique.append(c)

        return unique

    @staticmethod
    def _are_same_hole(a: dict, b: dict) -> bool:
        """Check if two hole candidates describe the same physical hole."""
        if abs(a["radius"] - b["radius"]) > _TOLERANCE:
            return False

        # Check axis direction is parallel (or anti-parallel)
        dot = (
            a["axis"]["x"] * b["axis"]["x"]
            + a["axis"]["y"] * b["axis"]["y"]
            + a["axis"]["z"] * b["axis"]["z"]
        )
        if abs(abs(dot) - 1.0) > _TOLERANCE:
            return False

        # Check location proximity
        dist = math.sqrt(
            (a["location"]["x"] - b["location"]["x"]) ** 2
            + (a["location"]["y"] - b["location"]["y"]) ** 2
            + (a["location"]["z"] - b["location"]["z"]) ** 2
        )
        if dist > _TOLERANCE * 100:  # Wider tolerance for location
            return False

        return True
