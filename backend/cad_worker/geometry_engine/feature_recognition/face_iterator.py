"""
face_iterator — shared helper for iterating shape faces with BSpline classification.

Provides a unified way for all feature detectors to iterate faces while
transparently classifying BSpline surfaces as analytic equivalents.

This avoids duplicating the BSpline classification logic across every detector.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("cad_worker.face_iterator")


@dataclass
class FaceInfo:
    """A single face with its effective analytic classification."""
    face: Any                   # TopoDS_Face
    effective_type: int         # GeomAbs_SurfaceType value
    surface: Any                # Geom_Surface (underlying)
    adaptor: Any                # GeomAdaptor_Surface
    # BSpline classification (only set for classified BSpline faces)
    bspline_radius: float | None = None
    bspline_axis: dict | None = None            # {x, y, z}
    bspline_location: dict | None = None        # {x, y, z}
    bspline_normal: dict | None = None          # {x, y, z} for planes
    bspline_plane_d: float | None = None        # signed dist for planes


def iter_faces(shape: Any) -> list[FaceInfo]:
    """
    Walk all faces in a shape, classify BSpline surfaces, and return
    FaceInfo objects with effective analytic surface types.

    Analytic faces (Plane, Cylinder, Cone, Sphere) are returned as-is.
    BSpline faces are classified via curvature analysis and returned with
    the effective analytic type + fitted parameters.

    Non-classifiable BSpline faces are returned with their original type.
    """
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.GeomAdaptor import GeomAdaptor_Surface
    from OCP.GeomAbs import (
        GeomAbs_Plane,
        GeomAbs_Cylinder,
        GeomAbs_Cone,
        GeomAbs_Sphere,
        GeomAbs_BSplineSurface,
    )
    from cad_worker.geometry_engine.bspline_classifier import (
        classify_bspline_face,
        SurfaceKind,
    )

    _KIND_TO_GEOMABS = {
        SurfaceKind.PLANE: GeomAbs_Plane,
        SurfaceKind.CYLINDER: GeomAbs_Cylinder,
        SurfaceKind.CONE: GeomAbs_Cone,
        SurfaceKind.SPHERE: GeomAbs_Sphere,
    }

    results: list[FaceInfo] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)

    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        surface = BRep_Tool.Surface_s(face)

        if surface is not None:
            adaptor = GeomAdaptor_Surface(surface)
            stype = adaptor.GetType()

            if stype == GeomAbs_BSplineSurface:
                # Attempt classification
                classified = classify_bspline_face(face)
                eff_type = _KIND_TO_GEOMABS.get(classified.kind, stype)
                results.append(FaceInfo(
                    face=face,
                    effective_type=eff_type,
                    surface=surface,
                    adaptor=adaptor,
                    bspline_radius=classified.radius,
                    bspline_axis=classified.axis,
                    bspline_location=classified.location,
                    bspline_normal=classified.normal,
                    bspline_plane_d=classified.plane_d,
                ))
            else:
                results.append(FaceInfo(
                    face=face,
                    effective_type=stype,
                    surface=surface,
                    adaptor=adaptor,
                ))

        explorer.Next()

    bspline_classified = sum(
        1 for fi in results
        if fi.bspline_normal is not None or fi.bspline_radius is not None
    )
    if bspline_classified > 0:
        logger.info(
            f"Face iteration: {len(results)} faces total, "
            f"{bspline_classified} BSpline faces classified as analytic"
        )

    return results
