"""
SQLAlchemy model for the models (CAD files) table.
Owned exclusively by CAD Service.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class CADModel(Base):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_format: Mapped[str] = mapped_column(String(20), nullable=False)  # STEP, IGES, STL, etc.
    gcs_path: Mapped[str] = mapped_column(Text, nullable=True)  # path in Cloud Storage
    gltf_path: Mapped[str] = mapped_column(Text, nullable=True)  # glTF output path
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum("UPLOADED", "PROCESSING", "READY", "FAILED", name="model_status"),
        default="UPLOADED",
        nullable=False,
    )
    visibility: Mapped[str] = mapped_column(
        SAEnum("PRIVATE", "PUBLIC", name="model_visibility"),
        default="PRIVATE",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<CADModel id={self.id} name={self.name} status={self.status}>"
