"""
SQLAlchemy model for the model_geometry table.

Stores deterministic geometry metrics extracted by the CAD Worker.
One-to-one relationship with CADModel (models table).
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db import Base


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
