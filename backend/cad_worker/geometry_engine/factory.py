"""
Geometry engine factory — selects the correct engine based on file extension.

Supported formats (MVP):
  • STEP  (.step, .stp)  → BRepGeometryEngine
  • IGES  (.iges, .igs)  → BRepGeometryEngine
  • STL   (.stl)         → MeshGeometryEngine

Parasolid is NOT supported in MVP.

Extensibility:
  Adding a new engine (e.g. ParasolidEngine) requires only:
    1. Create the new engine class extending GeometryEngineBase
    2. Add the extension mapping here
  No existing engine code is modified (Open/Closed Principle).
"""

from __future__ import annotations

import logging

from cad_worker.geometry_engine.base import GeometryEngineBase
from cad_worker.geometry_engine.brep_engine import BRepGeometryEngine
from cad_worker.geometry_engine.mesh_engine import MeshGeometryEngine

logger = logging.getLogger("cad_worker.factory")


class UnsupportedFormatError(Exception):
    """Raised when a file extension has no registered geometry engine."""

    def __init__(self, extension: str) -> None:
        self.extension = extension
        super().__init__(f"Unsupported CAD format: '{extension}'")


# ── Extension → Engine mapping ───────────────────────────────────────────────
# Centralised registry. Keys are lowercase with leading dot.

_ENGINE_REGISTRY: dict[str, type[GeometryEngineBase]] = {
    ".step": BRepGeometryEngine,
    ".stp": BRepGeometryEngine,
    ".iges": BRepGeometryEngine,
    ".igs": BRepGeometryEngine,
    ".stl": MeshGeometryEngine,
}


def get_engine(file_extension: str) -> GeometryEngineBase:
    """
    Return the appropriate geometry engine instance for a file extension.

    Args:
        file_extension: File extension including the dot, e.g. ".step".
                        Case-insensitive.

    Returns:
        An instantiated GeometryEngineBase subclass.

    Raises:
        UnsupportedFormatError: If no engine is registered for the extension.
    """
    ext = file_extension.lower().strip()
    if not ext.startswith("."):
        ext = f".{ext}"

    engine_cls = _ENGINE_REGISTRY.get(ext)

    if engine_cls is None:
        logger.error(f"No geometry engine for extension: {ext}")
        raise UnsupportedFormatError(ext)

    engine = engine_cls()
    logger.info(f"Selected engine: {engine_cls.__name__} for extension '{ext}'")
    return engine
