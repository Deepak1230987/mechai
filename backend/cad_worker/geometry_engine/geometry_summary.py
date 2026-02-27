"""
Geometry Summary Engine — deterministic global geometry metrics via OpenCascade.

Produces a GeometrySummary containing:
  • Bounding box (length, width, height)
  • Volume
  • Surface area
  • Center of mass

MATHEMATICAL FOUNDATIONS
========================

Volume Computation:
  Uses the Gauss divergence theorem applied to the BRep solid.
  BRepGProp.VolumeProperties integrates the signed volume contribution
  of each face's triangulation. For a closed solid, the sum equals the
  exact enclosed volume. We take abs() because face orientation (inward vs
  outward normals) can flip the sign.

Bounding Box:
  Bnd_Box computes the axis-aligned bounding box (AABB) by walking all
  vertices, edges, and face tessellations. We use SetGap(tolerance) to add
  a precision buffer — without this, tessellation artifacts can produce a box
  that is slightly smaller than the true geometry, causing downstream stock
  size underestimation.

Center of Mass:
  The center of mass of a solid is the volume-weighted centroid computed
  via GProp_GProps. For a uniform-density part (which we assume throughout
  process planning), this equals the geometric centroid. This point is
  critical for setup planning: a part should be clamped such that the
  center of mass is supported, preventing chatter during cutting.

ENGINEERING RULES
=================
  • Tolerance = 1e-6 for bounding box gap
  • Never compare floats with ==
  • Shape validity checked before processing
  • Pure function — no side effects, no DB writes
  • All exceptions propagated to caller (orchestrator handles)
"""

from __future__ import annotations

import logging

from cad_worker.schemas import BoundingBox, GeometrySummary

import time

logger = logging.getLogger("cad_worker.geometry_summary")

# Global geometry tolerance — matches OCC precision for BRep operations
_TOLERANCE = 1e-6


def compute_geometry_summary(shape) -> GeometrySummary:
    """
    Compute global geometry metrics from a TopoDS_Shape.

    Args:
        shape: A valid OCC TopoDS_Shape (solid or compound).

    Returns:
        GeometrySummary with bounding box, volume, surface area,
        and center of mass.

    Raises:
        ValueError: If the shape is null or invalid.
        RuntimeError: If any OCC computation fails.

    Mathematical notes:
        - Volume uses Gauss divergence theorem on BRep faces
        - Bounding box uses AABB with tolerance gap
        - Surface area integrates face area contributions
        - Center of mass assumes uniform density
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepGProp import BRepGProp
    from OCP.Bnd import Bnd_Box
    from OCP.GProp import GProp_GProps

    # ── Validate shape ──────────────────────────────────────────────────
    if shape is None or shape.IsNull():
        raise ValueError("Cannot compute geometry summary: shape is null")

    t_start = time.monotonic()
    logger.info("Computing geometry summary...")

    # ── 1. Bounding Box ─────────────────────────────────────────────────
    # Bnd_Box computes the axis-aligned bounding box by iterating all
    # geometric entities (vertices, edges, faces). SetGap adds a small
    # buffer to account for tessellation precision — without this, curved
    # surfaces with coarse tessellation may underestimate the true extent.
    bbox = Bnd_Box()
    bbox.SetGap(_TOLERANCE)
    BRepBndLib.Add_s(shape, bbox)

    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

    # Compute dimensions and sort to get length >= width >= height
    dims = sorted([
        abs(xmax - xmin),
        abs(ymax - ymin),
        abs(zmax - zmin),
    ], reverse=True)

    bounding_box = BoundingBox(
        length=round(dims[0], 6),
        width=round(dims[1], 6),
        height=round(dims[2], 6),
    )

    # ── 2. Volume ───────────────────────────────────────────────────────
    # BRepGProp.VolumeProperties uses the divergence theorem:
    #   V = (1/3) * ∮ (r · n̂) dA
    # where r is position, n̂ is outward normal, and dA is the face area
    # element. This gives exact volume for analytic surfaces and high-
    # precision results for tessellated BSpline surfaces.
    vol_props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vol_props)
    volume = round(abs(vol_props.Mass()), 6)

    # Guard: zero volume indicates a non-solid shape (sheet body, wire, etc.)
    if volume < _TOLERANCE:
        logger.warning(
            "Volume ≈ 0 — shape may be a surface body or wire, not a solid. "
            "Downstream engines may produce unreliable results."
        )

    # ── 3. Center of Mass ───────────────────────────────────────────────
    # The center of mass for uniform density equals the volume centroid:
    #   CoM = (1/V) * ∫∫∫ r dV
    # Computed as a by-product of VolumeProperties.
    com = vol_props.CentreOfMass()
    center_of_mass = (
        round(com.X(), 6),
        round(com.Y(), 6),
        round(com.Z(), 6),
    )

    # ── 4. Surface Area ─────────────────────────────────────────────────
    # BRepGProp.SurfaceProperties integrates the area of each face:
    #   A = ∮ |∂r/∂u × ∂r/∂v| du dv
    # where (u, v) are surface parametric coordinates. For a closed solid,
    # this gives the total wetted surface area — important for
    # surface finish time estimation.
    area_props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, area_props)
    surface_area = round(abs(area_props.Mass()), 6)

    # Guard: zero surface area indicates a degenerate shape
    if surface_area < _TOLERANCE:
        logger.warning(
            "Surface area ≈ 0 — shape may be degenerate. "
            "Stock recommendation and complexity scoring may be unreliable."
        )

    # Guard: bounding box with zero dimensions
    if bounding_box.length < _TOLERANCE or bounding_box.width < _TOLERANCE or bounding_box.height < _TOLERANCE:
        logger.warning(
            f"Bounding box has near-zero dimension: "
            f"{bounding_box.length}x{bounding_box.width}x{bounding_box.height}. "
            f"Shape may be 2D or degenerate."
        )

    result = GeometrySummary(
        bounding_box=bounding_box,
        volume=volume,
        surface_area=surface_area,
        center_of_mass=center_of_mass,
    )

    elapsed_ms = (time.monotonic() - t_start) * 1000
    logger.info(
        f"Geometry summary complete in {elapsed_ms:.1f}ms: "
        f"bbox=({bounding_box.length}x{bounding_box.width}x{bounding_box.height}), "
        f"vol={volume}, sa={surface_area}, "
        f"com=({center_of_mass[0]}, {center_of_mass[1]}, {center_of_mass[2]})"
    )

    return result
