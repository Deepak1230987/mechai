"""
Mesh Geometry Engine — STL processing via trimesh / numpy.

Extracts deterministic geometry metrics from triangulated mesh data:
  • Bounding box (axis-aligned, from vertices)
  • Surface area (triangle summation)
  • Volume (only if the mesh is watertight / closed)

No analytic face classification is possible for meshes.
All face counts are 0 and feature_ready is False.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import trimesh

from cad_worker.geometry_engine.base import GeometryEngineBase
from cad_worker.schemas import GeometryResult

logger = logging.getLogger("cad_worker.mesh_engine")


class MeshGeometryEngine(GeometryEngineBase):
    """
    Processes STL (.stl) files using trimesh.

    All returned results have geometry_type="MESH", feature_ready=False,
    and all analytic face counts set to 0.
    """

    # ── Public API ───────────────────────────────────────────────────────────

    def extract_geometry(self, file_path: str | Path) -> GeometryResult:
        """
        Full extraction pipeline for an STL mesh file.

        1. Load mesh from STL
        2. Compute bounding box from vertices
        3. Compute surface area from triangle areas
        4. Compute volume (only if mesh is watertight)

        Returns GeometryResult with feature_ready=False.
        """
        file_path = Path(file_path)
        logger.info(f"Mesh extraction started: {file_path.name}")

        try:
            mesh = self.load_mesh(file_path)
            bbox = self.compute_bounding_box(mesh)
            surface_area = self.compute_surface_area(mesh)
            volume = self.compute_volume_if_closed(mesh)

            result = GeometryResult(
                geometry_type="MESH",
                bounding_box=bbox,
                volume=volume,
                surface_area=surface_area,
                planar_faces=0,
                cylindrical_faces=0,
                conical_faces=0,
                spherical_faces=0,
                feature_ready=False,
            )
            logger.info(
                f"Mesh extraction complete: {file_path.name} — "
                f"vol={volume:.4f}, sa={surface_area:.4f}, "
                f"watertight={mesh.is_watertight}, "
                f"faces={len(mesh.faces)}, vertices={len(mesh.vertices)}"
            )
            return result

        except Exception as e:
            logger.error(f"Mesh extraction failed for {file_path.name}: {e}")
            raise

    # ── Mesh loading ─────────────────────────────────────────────────────────

    def load_mesh(self, file_path: Path) -> trimesh.Trimesh:
        """
        Load an STL file into a trimesh.Trimesh object.

        Raises:
            ValueError: If the loaded object is not a valid mesh.
            FileNotFoundError: If the file does not exist.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"STL file not found: {file_path}")

        loaded = trimesh.load(
            str(file_path),
            file_type="stl",
            force="mesh",  # Collapse Scene → single Trimesh
        )

        if not isinstance(loaded, trimesh.Trimesh):
            raise ValueError(
                f"Expected Trimesh, got {type(loaded).__name__} from {file_path.name}"
            )

        if len(loaded.vertices) == 0 or len(loaded.faces) == 0:
            raise ValueError(f"STL file contains no geometry: {file_path.name}")

        logger.info(
            f"STL loaded: {file_path.name} — "
            f"{len(loaded.faces)} faces, {len(loaded.vertices)} vertices"
        )
        return loaded

    # ── Bounding box ─────────────────────────────────────────────────────────

    def compute_bounding_box(self, mesh: trimesh.Trimesh) -> dict:
        """
        Compute the axis-aligned bounding box from mesh vertices.

        Returns:
            dict with keys: xmin, ymin, zmin, xmax, ymax, zmax,
                            x_size, y_size, z_size
        """
        vertices = mesh.vertices  # (N, 3) numpy array
        mins = vertices.min(axis=0)
        maxs = vertices.max(axis=0)

        return {
            "xmin": round(float(mins[0]), 6),
            "ymin": round(float(mins[1]), 6),
            "zmin": round(float(mins[2]), 6),
            "xmax": round(float(maxs[0]), 6),
            "ymax": round(float(maxs[1]), 6),
            "zmax": round(float(maxs[2]), 6),
            "x_size": round(float(maxs[0] - mins[0]), 6),
            "y_size": round(float(maxs[1] - mins[1]), 6),
            "z_size": round(float(maxs[2] - mins[2]), 6),
        }

    # ── Surface area ─────────────────────────────────────────────────────────

    def compute_surface_area(self, mesh: trimesh.Trimesh) -> float:
        """
        Compute total surface area by summing individual triangle areas.
        trimesh provides this as mesh.area.
        """
        area = float(mesh.area)
        return round(abs(area), 6)

    # ── Volume ───────────────────────────────────────────────────────────────

    def compute_volume_if_closed(self, mesh: trimesh.Trimesh) -> float:
        """
        Compute volume only if the mesh is watertight (closed).

        For non-watertight meshes, volume is physically meaningless,
        so we return 0.0.
        """
        if mesh.is_watertight:
            volume = float(mesh.volume)
            return round(abs(volume), 6)

        logger.warning(
            "Mesh is not watertight — volume cannot be computed reliably. "
            "Returning 0.0."
        )
        return 0.0
