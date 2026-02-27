"""
BSpline Surface Classifier — determine analytic type of BSpline surfaces.

IGES files (and some STEP files) import all surfaces as BSpline even when the
underlying geometry is a simple plane, cylinder, cone, or sphere.  This module
samples curvature at multiple UV points on a BSpline surface and fits it to
the closest analytic type.

Classification rules (based on principal curvatures κ_min, κ_max):
┌───────────┬──────────────────────────────────────────────────────┐
│ Type      │ Criterion                                            │
├───────────┼──────────────────────────────────────────────────────┤
│ Plane     │ GeomLib_IsPlanarSurface (built-in OCP) OR            │
│           │ both κ_min ≈ 0 and κ_max ≈ 0 at all sample points   │
├───────────┼──────────────────────────────────────────────────────┤
│ Cylinder  │ κ_min ≈ 0 everywhere, κ_max ≈ constant ≠ 0          │
│           │ (radius R = 1 / |κ_max|)                             │
├───────────┼──────────────────────────────────────────────────────┤
│ Sphere    │ κ_min ≈ κ_max ≈ constant ≠ 0                        │
│           │ (radius R = 1 / |κ|)                                 │
├───────────┼──────────────────────────────────────────────────────┤
│ Cone      │ κ_min ≈ 0 everywhere, κ_max varies monotonically     │
│           │ along one direction but nonzero everywhere            │
└───────────┴──────────────────────────────────────────────────────┘

Returns: ClassifiedSurface with effective_type and fitted analytic parameters.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("cad_worker.bspline_classifier")


# ── Result types ──────────────────────────────────────────────────────────────

class SurfaceKind(str, Enum):
    PLANE = "PLANE"
    CYLINDER = "CYLINDER"
    CONE = "CONE"
    SPHERE = "SPHERE"
    OTHER = "OTHER"


@dataclass(frozen=True)
class ClassifiedSurface:
    """Result of classifying a BSpline surface."""
    kind: SurfaceKind
    radius: float | None = None          # for cylinder, sphere, cone
    axis: dict | None = None             # {x, y, z} for cylinder/cone
    location: dict | None = None         # {x, y, z} centre point
    normal: dict | None = None           # {x, y, z} for plane
    plane_d: float | None = None         # signed distance from origin (plane)
    confidence: float = 0.0              # 0.0–1.0


# ── Tolerances ────────────────────────────────────────────────────────────────

_CURVATURE_ZERO_TOL = 1e-3       # |κ| below this → "zero"
_CURVATURE_VARIATION_TOL = 0.15  # relative std / mean must be < this to be "constant"
_PLANAR_LINEAR_TOL = 1e-3        # GeomLib_IsPlanarSurface tolerance
_SAMPLE_GRID = 5                 # NxN sample grid in UV space


# ── Public API ────────────────────────────────────────────────────────────────

def classify_bspline_face(face: Any, tolerance: float = _PLANAR_LINEAR_TOL) -> ClassifiedSurface:
    """
    Classify a BSpline TopoDS_Face into an analytic surface type.

    Args:
        face:       A TopoDS_Face with a BSpline underlying surface.
        tolerance:  Linear tolerance for planarity check.

    Returns:
        ClassifiedSurface with the effective type and fitted parameters.
    """
    from OCP.BRep import BRep_Tool
    from OCP.GeomAdaptor import GeomAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_BSplineSurface

    surface = BRep_Tool.Surface_s(face)
    if surface is None:
        return ClassifiedSurface(kind=SurfaceKind.OTHER, confidence=0.0)

    adaptor = GeomAdaptor_Surface(surface)
    stype = adaptor.GetType()

    # Only classify BSpline surfaces — analytic types are already known
    if stype != GeomAbs_BSplineSurface:
        return ClassifiedSurface(kind=SurfaceKind.OTHER, confidence=0.0)

    # ── 1. Quick planarity check via OCP built-in ────────────────────────
    plane_result = _check_planar(surface, tolerance)
    if plane_result is not None:
        return plane_result

    # ── 2. Sample curvatures ─────────────────────────────────────────────
    curvatures = _sample_curvatures(face)
    if not curvatures:
        return ClassifiedSurface(kind=SurfaceKind.OTHER, confidence=0.0)

    # ── 3. Classify from curvature pattern ───────────────────────────────
    return _classify_from_curvatures(curvatures, face)


def classify_all_faces(shape: Any) -> list[tuple[Any, ClassifiedSurface]]:
    """
    Walk all faces in a shape and classify BSpline ones.

    Returns list of (face, ClassifiedSurface) for BSpline faces only.
    Analytic faces are not included (they don't need classification).
    """
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.BRep import BRep_Tool
    from OCP.GeomAdaptor import GeomAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_BSplineSurface

    results = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)

    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        surface = BRep_Tool.Surface_s(face)

        if surface is not None:
            adaptor = GeomAdaptor_Surface(surface)
            if adaptor.GetType() == GeomAbs_BSplineSurface:
                classified = classify_bspline_face(face)
                results.append((face, classified))

        explorer.Next()

    return results


# ── Internal helpers ──────────────────────────────────────────────────────────

def _check_planar(surface: Any, tolerance: float) -> ClassifiedSurface | None:
    """Use OCP's built-in GeomLib_IsPlanarSurface to check planarity."""
    try:
        from OCP.GeomLib import GeomLib_IsPlanarSurface

        checker = GeomLib_IsPlanarSurface(surface, tolerance)
        if checker.IsPlanar():
            plane = checker.Plan()
            ax = plane.Axis().Direction()
            loc = plane.Location()
            normal = {"x": ax.X(), "y": ax.Y(), "z": ax.Z()}
            plane_d = loc.X() * ax.X() + loc.Y() * ax.Y() + loc.Z() * ax.Z()
            return ClassifiedSurface(
                kind=SurfaceKind.PLANE,
                normal=normal,
                plane_d=plane_d,
                location={"x": loc.X(), "y": loc.Y(), "z": loc.Z()},
                confidence=0.95,
            )
    except Exception as e:
        logger.debug(f"GeomLib_IsPlanarSurface failed: {e}")

    return None


@dataclass
class _CurvatureSample:
    """Curvature at a single UV point."""
    u: float
    v: float
    k_min: float
    k_max: float
    normal: tuple[float, float, float]
    point: tuple[float, float, float]


def _sample_curvatures(face: Any, n: int = _SAMPLE_GRID) -> list[_CurvatureSample]:
    """
    Sample principal curvatures at an NxN grid of UV points on the face.

    Uses BRepAdaptor_Surface + BRepLProp_SLProps for robust face-local
    UV parameterisation.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps

    try:
        adaptor = BRepAdaptor_Surface(face)
        u_min = adaptor.FirstUParameter()
        u_max = adaptor.LastUParameter()
        v_min = adaptor.FirstVParameter()
        v_max = adaptor.LastVParameter()

        # Clamp range for periodic surfaces (avoid wrapping artefacts)
        u_range = u_max - u_min
        v_range = v_max - v_min
        margin = 0.05  # 5% from boundaries
        u_start = u_min + u_range * margin
        u_end = u_max - u_range * margin
        v_start = v_min + v_range * margin
        v_end = v_max - v_range * margin

        samples: list[_CurvatureSample] = []

        for i in range(n):
            u = u_start + (u_end - u_start) * i / max(n - 1, 1)
            for j in range(n):
                v = v_start + (v_end - v_start) * j / max(n - 1, 1)

                props = BRepLProp_SLProps(adaptor, u, v, 2, 1e-6)
                if not props.IsCurvatureDefined():
                    continue

                try:
                    k_min = props.MinCurvature()
                    k_max = props.MaxCurvature()
                    normal_dir = props.Normal()
                    point = props.Value()

                    samples.append(_CurvatureSample(
                        u=u, v=v,
                        k_min=k_min, k_max=k_max,
                        normal=(normal_dir.X(), normal_dir.Y(), normal_dir.Z()),
                        point=(point.X(), point.Y(), point.Z()),
                    ))
                except Exception:
                    continue

        return samples

    except Exception as e:
        logger.debug(f"Curvature sampling failed: {e}")
        return []


def _classify_from_curvatures(
    samples: list[_CurvatureSample],
    face: Any,
) -> ClassifiedSurface:
    """
    Determine the analytic surface type from curvature samples.

    Applies the curvature-based classification rules described in the
    module docstring.
    """
    if len(samples) < 4:
        return ClassifiedSurface(kind=SurfaceKind.OTHER, confidence=0.0)

    k_mins = [s.k_min for s in samples]
    k_maxs = [s.k_max for s in samples]

    all_k_min_zero = all(abs(k) < _CURVATURE_ZERO_TOL for k in k_mins)
    all_k_max_zero = all(abs(k) < _CURVATURE_ZERO_TOL for k in k_maxs)

    # ── Plane: both curvatures ≈ 0 ──────────────────────────────────────
    if all_k_min_zero and all_k_max_zero:
        return _build_plane_from_normals(samples)

    # Separate the "small" and "big" curvatures
    # Convention: |k_min| ≤ |k_max| (OCP guarantees this)
    abs_k_maxs = [abs(k) for k in k_maxs]
    abs_k_mins = [abs(k) for k in k_mins]

    # ── Cylinder: κ_min ≈ 0, κ_max ≈ constant ≠ 0 ───────────────────────
    if all_k_min_zero and not all_k_max_zero:
        if _is_constant(abs_k_maxs):
            mean_k = sum(abs_k_maxs) / len(abs_k_maxs)
            radius = 1.0 / mean_k if mean_k > 1e-10 else 0.0
            axis_info = _estimate_cylinder_axis(samples)
            return ClassifiedSurface(
                kind=SurfaceKind.CYLINDER,
                radius=radius,
                axis=axis_info.get("direction"),
                location=axis_info.get("point"),
                confidence=0.85,
            )

        # ── Cone: κ_min ≈ 0, κ_max varies (but nonzero everywhere) ──────
        if all(k > _CURVATURE_ZERO_TOL for k in abs_k_maxs):
            mean_k = sum(abs_k_maxs) / len(abs_k_maxs)
            radius = 1.0 / mean_k if mean_k > 1e-10 else 0.0
            axis_info = _estimate_cylinder_axis(samples)  # approximation
            return ClassifiedSurface(
                kind=SurfaceKind.CONE,
                radius=radius,
                axis=axis_info.get("direction"),
                location=axis_info.get("point"),
                confidence=0.65,
            )

    # ── Sphere: κ_min ≈ κ_max ≈ constant ≠ 0 ────────────────────────────
    if not all_k_min_zero and not all_k_max_zero:
        # Check that k_min ≈ k_max at each point
        ratios = [
            abs(s.k_min / s.k_max) if abs(s.k_max) > 1e-10 else 0.0
            for s in samples
        ]
        if all(0.85 < r < 1.15 for r in ratios if r > 0):
            if _is_constant(abs_k_maxs) and _is_constant(abs_k_mins):
                mean_k = sum(abs_k_maxs) / len(abs_k_maxs)
                radius = 1.0 / mean_k if mean_k > 1e-10 else 0.0
                centre = _estimate_sphere_centre(samples, radius)
                return ClassifiedSurface(
                    kind=SurfaceKind.SPHERE,
                    radius=radius,
                    location=centre,
                    confidence=0.80,
                )

    return ClassifiedSurface(kind=SurfaceKind.OTHER, confidence=0.0)


# ── Statistics helpers ────────────────────────────────────────────────────────

def _is_constant(values: list[float]) -> bool:
    """Check if a list of positive values is approximately constant."""
    if not values:
        return False
    mean = sum(values) / len(values)
    if mean < 1e-10:
        return True  # all effectively zero
    std = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
    return (std / mean) < _CURVATURE_VARIATION_TOL


def _build_plane_from_normals(samples: list[_CurvatureSample]) -> ClassifiedSurface:
    """Build a plane classification from consistent normals."""
    nx = sum(s.normal[0] for s in samples) / len(samples)
    ny = sum(s.normal[1] for s in samples) / len(samples)
    nz = sum(s.normal[2] for s in samples) / len(samples)
    mag = math.sqrt(nx * nx + ny * ny + nz * nz)
    if mag < 1e-10:
        return ClassifiedSurface(kind=SurfaceKind.OTHER, confidence=0.0)
    nx, ny, nz = nx / mag, ny / mag, nz / mag

    # Average point → compute plane_d
    px = sum(s.point[0] for s in samples) / len(samples)
    py = sum(s.point[1] for s in samples) / len(samples)
    pz = sum(s.point[2] for s in samples) / len(samples)
    plane_d = px * nx + py * ny + pz * nz

    return ClassifiedSurface(
        kind=SurfaceKind.PLANE,
        normal={"x": nx, "y": ny, "z": nz},
        plane_d=plane_d,
        location={"x": px, "y": py, "z": pz},
        confidence=0.85,
    )


def _estimate_cylinder_axis(
    samples: list[_CurvatureSample],
) -> dict:
    """
    Estimate the cylinder axis direction from surface normals.

    For a cylinder, all normals are perpendicular to the axis.
    The axis direction is the cross product of two non-parallel normals,
    averaged over all pairs.
    """
    # Find two normals with maximum angular separation
    best_cross = None
    best_cross_mag = 0.0

    n0 = samples[0].normal
    for s in samples[1:]:
        n1 = s.normal
        cx = n0[1] * n1[2] - n0[2] * n1[1]
        cy = n0[2] * n1[0] - n0[0] * n1[2]
        cz = n0[0] * n1[1] - n0[1] * n1[0]
        mag = math.sqrt(cx * cx + cy * cy + cz * cz)
        if mag > best_cross_mag:
            best_cross = (cx, cy, cz)
            best_cross_mag = mag

    if best_cross is None or best_cross_mag < 1e-10:
        return {}

    dx = best_cross[0] / best_cross_mag
    dy = best_cross[1] / best_cross_mag
    dz = best_cross[2] / best_cross_mag

    # Estimate axis centre: average of (point - radius * normal)
    mean_k = sum(abs(s.k_max) for s in samples) / len(samples)
    radius = 1.0 / mean_k if mean_k > 1e-10 else 0.0

    cx = sum(s.point[0] - radius * s.normal[0] for s in samples) / len(samples)
    cy = sum(s.point[1] - radius * s.normal[1] for s in samples) / len(samples)
    cz = sum(s.point[2] - radius * s.normal[2] for s in samples) / len(samples)

    return {
        "direction": {"x": dx, "y": dy, "z": dz},
        "point": {"x": cx, "y": cy, "z": cz},
    }


def _estimate_sphere_centre(
    samples: list[_CurvatureSample],
    radius: float,
) -> dict:
    """Estimate sphere centre from point + normal + radius."""
    cx = sum(s.point[0] - radius * s.normal[0] for s in samples) / len(samples)
    cy = sum(s.point[1] - radius * s.normal[1] for s in samples) / len(samples)
    cz = sum(s.point[2] - radius * s.normal[2] for s in samples) / len(samples)
    return {"x": cx, "y": cy, "z": cz}
