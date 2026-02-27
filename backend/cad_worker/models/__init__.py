"""
SQLAlchemy models for the CAD Worker domain.

  • ModelGeometry — deterministic geometry metrics (one-to-one with CADModel)
  • ModelFeature  — detected machining features (one-to-many with CADModel)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SAEnum,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


# ── ModelGeometry ─────────────────────────────────────────────────────────────

class ModelGeometry(Base):
    __tablename__ = "model_geometry"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    model_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    geometry_type: Mapped[str] = mapped_column(
        SAEnum("BREP", "MESH", name="geometry_type_enum"),
        nullable=False,
    )
    bounding_box: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    volume: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    surface_area: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Analytic face counts — only meaningful for BREP; 0 for MESH
    planar_faces: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cylindrical_faces: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conical_faces: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spherical_faces: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    feature_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Phase A: Manufacturing Geometry Intelligence Engine
    # Stores the full ManufacturingGeometryReport as JSONB
    manufacturing_intelligence_report: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        comment="Full ManufacturingGeometryReport (Phase A intelligence)",
    )
    intelligence_ready: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="True when manufacturing intelligence report is available",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ModelGeometry id={self.id} model_id={self.model_id} "
            f"type={self.geometry_type} feature_ready={self.feature_ready}>"
        )


# ── ModelFeature ──────────────────────────────────────────────────────────────

class ModelFeature(Base):
    """
    A single detected machining feature on a CAD model.

    Feature types: HOLE, POCKET, SLOT, TURN_PROFILE
    Only created for BREP models (feature_ready == True).
    """
    __tablename__ = "model_features"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    model_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(
        SAEnum(
            "HOLE", "POCKET", "SLOT", "TURN_PROFILE",
            name="feature_type_enum",
        ),
        nullable=False,
    )
    dimensions: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Feature-specific dimensions (diameter, length, width, depth, etc.)",
    )
    depth: Mapped[float | None] = mapped_column(Float, nullable=True)
    diameter: Mapped[float | None] = mapped_column(Float, nullable=True)
    axis: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Axis direction vector {x, y, z}",
    )
    tolerance: Mapped[float | None] = mapped_column(Float, nullable=True)
    surface_finish: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ModelFeature id={self.id} model_id={self.model_id} "
            f"type={self.type} confidence={self.confidence}>"
        )
