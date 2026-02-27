"""
BRep Geometry Engine — STEP / IGES processing via pythonOCC (OCP).

Extracts deterministic geometry metrics from analytic BRep data:
  • Bounding box (axis-aligned)
  • Volume
  • Surface area
  • Face classification (planar, cylindrical, conical, spherical)

All OCC calls are wrapped in try/except to prevent worker crashes.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cad_worker.geometry_engine.base import GeometryEngineBase
from cad_worker.schemas import GeometryResult

logger = logging.getLogger("cad_worker.brep_engine")


class BRepGeometryEngine(GeometryEngineBase):
    """
    Processes STEP (.step, .stp) and IGES (.iges, .igs) files
    using OpenCascade (pythonOCC / OCP).

    All returned results have geometry_type="BREP" and feature_ready=True.
    """

    # ── File extension → reader mapping ──────────────────────────────────────
    _STEP_EXTENSIONS = {".step", ".stp"}
    _IGES_EXTENSIONS = {".iges", ".igs"}

    # ── Public API ───────────────────────────────────────────────────────────

    def extract_geometry(self, file_path: str | Path) -> GeometryResult:
        """
        Full extraction pipeline for a BRep file.

        1. Load shape from STEP or IGES
        2. Compute bounding box
        3. Compute volume
        4. Compute surface area
        5. Classify analytic faces

        Returns GeometryResult with feature_ready=True.
        """
        file_path = Path(file_path)
        logger.info(f"BRep extraction started: {file_path.name}")

        try:
            shape = self.load_shape(file_path)
            bbox = self.compute_bounding_box(shape)
            volume = self.compute_volume(shape)
            surface_area = self.compute_surface_area(shape)
            face_counts = self.classify_faces(shape)

            result = GeometryResult(
                geometry_type="BREP",
                bounding_box=bbox,
                volume=volume,
                surface_area=surface_area,
                planar_faces=face_counts["planar"],
                cylindrical_faces=face_counts["cylindrical"],
                conical_faces=face_counts["conical"],
                spherical_faces=face_counts["spherical"],
                feature_ready=True,
            )
            logger.info(
                f"BRep extraction complete: {file_path.name} — "
                f"vol={volume:.4f}, sa={surface_area:.4f}, "
                f"faces(P={face_counts['planar']}, "
                f"Cy={face_counts['cylindrical']}, "
                f"Co={face_counts['conical']}, "
                f"S={face_counts['spherical']})"
            )
            return result

        except Exception as e:
            logger.error(f"BRep extraction failed for {file_path.name}: {e}")
            raise

    # ── Shape loading ────────────────────────────────────────────────────────

    def load_shape(self, file_path: Path):
        """
        Load a TopoDS_Shape from a STEP or IGES file.

        Raises:
            ValueError: If file extension is unsupported or shape is null.
            RuntimeError: If the OCC reader fails to parse.
        """
        from OCP.IFSelect import IFSelect_RetDone

        ext = file_path.suffix.lower()

        if ext in self._STEP_EXTENSIONS:
            return self._read_step(file_path)
        elif ext in self._IGES_EXTENSIONS:
            return self._read_iges(file_path)
        else:
            raise ValueError(f"BRepGeometryEngine does not support extension: {ext}")

    def _read_step(self, file_path: Path):
        """Read a STEP file using STEPControl_Reader."""
        from OCP.STEPControl import STEPControl_Reader
        from OCP.IFSelect import IFSelect_RetDone

        reader = STEPControl_Reader()
        status = reader.ReadFile(str(file_path))

        if status != IFSelect_RetDone:
            raise RuntimeError(
                f"STEP reader failed with status {status} for {file_path.name}"
            )

        reader.TransferRoots()
        shape = reader.OneShape()

        if shape is None or shape.IsNull():
            raise ValueError(f"STEP file produced a null shape: {file_path.name}")

        logger.info(f"STEP loaded: {file_path.name}")
        return shape

    def _read_iges(self, file_path: Path):
        """Read an IGES file using IGESControl_Reader."""
        from OCP.IGESControl import IGESControl_Reader
        from OCP.IFSelect import IFSelect_RetDone

        reader = IGESControl_Reader()
        status = reader.ReadFile(str(file_path))

        if status != IFSelect_RetDone:
            raise RuntimeError(
                f"IGES reader failed with status {status} for {file_path.name}"
            )

        reader.TransferRoots()
        shape = reader.OneShape()

        if shape is None or shape.IsNull():
            raise ValueError(f"IGES file produced a null shape: {file_path.name}")

        logger.info(f"IGES loaded: {file_path.name}")
        return shape

    # ── Bounding box ─────────────────────────────────────────────────────────

    def compute_bounding_box(self, shape) -> dict:
        """
        Compute the axis-aligned bounding box of a shape.

        Returns:
            dict with keys: xmin, ymin, zmin, xmax, ymax, zmax,
                            x_size, y_size, z_size
        """
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        try:
            bbox = Bnd_Box()
            BRepBndLib.Add_s(shape, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

            return {
                "xmin": round(xmin, 6),
                "ymin": round(ymin, 6),
                "zmin": round(zmin, 6),
                "xmax": round(xmax, 6),
                "ymax": round(ymax, 6),
                "zmax": round(zmax, 6),
                "x_size": round(xmax - xmin, 6),
                "y_size": round(ymax - ymin, 6),
                "z_size": round(zmax - zmin, 6),
            }
        except Exception as e:
            logger.error(f"Bounding box computation failed: {e}")
            raise

    # ── Volume ───────────────────────────────────────────────────────────────

    def compute_volume(self, shape) -> float:
        """Compute the volume of a solid shape using GProp_GProps."""
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp

        try:
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(shape, props)
            volume = props.Mass()
            return round(abs(volume), 6)
        except Exception as e:
            logger.error(f"Volume computation failed: {e}")
            raise

    # ── Surface area ─────────────────────────────────────────────────────────

    def compute_surface_area(self, shape) -> float:
        """Compute total surface area using GProp_GProps."""
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp

        try:
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(shape, props)
            area = props.Mass()
            return round(abs(area), 6)
        except Exception as e:
            logger.error(f"Surface area computation failed: {e}")
            raise

    # ── Face classification ──────────────────────────────────────────────────

    def classify_faces(self, shape) -> dict:
        """
        Iterate all faces in the shape, classify each by surface type.

        Uses TopExp_Explorer to walk TopAbs_FACE entries and
        GeomAdaptor_Surface to determine the analytic surface type.
        Falls back to BSpline curvature classification for NURBS faces.

        Returns:
            dict with keys: planar, cylindrical, conical, spherical
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

        counts = {
            "planar": 0,
            "cylindrical": 0,
            "conical": 0,
            "spherical": 0,
        }

        try:
            explorer = TopExp_Explorer(shape, TopAbs_FACE)

            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())
                surface = BRep_Tool.Surface_s(face)

                if surface is not None:
                    adaptor = GeomAdaptor_Surface(surface)
                    surface_type = adaptor.GetType()

                    if surface_type == GeomAbs_Plane:
                        counts["planar"] += 1
                    elif surface_type == GeomAbs_Cylinder:
                        counts["cylindrical"] += 1
                    elif surface_type == GeomAbs_Cone:
                        counts["conical"] += 1
                    elif surface_type == GeomAbs_Sphere:
                        counts["spherical"] += 1
                    elif surface_type == GeomAbs_BSplineSurface:
                        # Attempt to classify BSpline as analytic
                        classified = classify_bspline_face(face)
                        if classified.kind == SurfaceKind.PLANE:
                            counts["planar"] += 1
                        elif classified.kind == SurfaceKind.CYLINDER:
                            counts["cylindrical"] += 1
                        elif classified.kind == SurfaceKind.CONE:
                            counts["conical"] += 1
                        elif classified.kind == SurfaceKind.SPHERE:
                            counts["spherical"] += 1
                    # Other surface types (torus, bspline-other, etc.) not counted

                explorer.Next()

        except Exception as e:
            logger.error(f"Face classification failed: {e}")
            raise

        return counts
