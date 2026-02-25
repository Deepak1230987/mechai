"""
GeometryResult — canonical output contract for all geometry engines.

Both BRepGeometryEngine and MeshGeometryEngine MUST return this exact structure.
This is a pure data class with no ORM dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GeometryResult:
    """
    Deterministic geometry metrics extracted from a CAD file.

    Attributes:
        geometry_type:    "BREP" for STEP/IGES, "MESH" for STL.
        bounding_box:     Axis-aligned bounding box with xmin..zmax and sizes.
        volume:           Part volume in model units³.
        surface_area:     Total surface area in model units².
        planar_faces:     Count of planar analytic faces (BRep only).
        cylindrical_faces: Count of cylindrical analytic faces (BRep only).
        conical_faces:    Count of conical analytic faces (BRep only).
        spherical_faces:  Count of spherical analytic faces (BRep only).
        feature_ready:    True if analytic face data is valid (BRep only).
    """

    geometry_type: str  # "BREP" | "MESH"
    bounding_box: dict = field(default_factory=dict)
    volume: float = 0.0
    surface_area: float = 0.0
    planar_faces: int = 0
    cylindrical_faces: int = 0
    conical_faces: int = 0
    spherical_faces: int = 0
    feature_ready: bool = False

    def __post_init__(self) -> None:
        if self.geometry_type not in ("BREP", "MESH"):
            raise ValueError(
                f"geometry_type must be 'BREP' or 'MESH', got '{self.geometry_type}'"
            )
