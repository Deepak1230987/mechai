"""
Abstract base class for all geometry engines.

Every engine must implement `extract_geometry(file_path) -> GeometryResult`.
This ensures the factory pattern works — the worker calls the same method
regardless of whether its a BRep or Mesh engine underneath.

Future engines (Parasolid, FeatureRecognition, etc.) extend this base
without modifying any existing engine code.
"""

from __future__ import annotations

import abc
from pathlib import Path

from cad_worker.schemas import GeometryResult


class GeometryEngineBase(abc.ABC):
    """
    Contract that all geometry engines must fulfil.

    Subclasses:
        BRepGeometryEngine  — STEP / IGES (pythonOCC)
        MeshGeometryEngine  — STL (trimesh / numpy)
    """

    @abc.abstractmethod
    def extract_geometry(self, file_path: str | Path) -> GeometryResult:
        """
        Parse a CAD file and return deterministic geometry metrics.

        Args:
            file_path: Absolute path to the downloaded CAD file on disk.

        Returns:
            GeometryResult with all fields populated per engine rules.

        Raises:
            Exception: If loading or processing fails. The caller
                       (worker.py) catches this and marks the model FAILED.
        """
        ...
