"""
SQLAlchemy models for the CAD Worker domain.

  • ModelGeometry — deterministic geometry metrics (one-to-one with CADModel)
  • ModelFeature  — detected machining features (one-to-many with CADModel)

TABLE RELATIONSHIPS
===================
  CADModel (cad_service)          1:1
     ├── ModelGeometry (cad_worker)     ← geometry + intelligence
     │     • bounding_box, volume, surface_area, face counts
     │     • manufacturing_intelligence_report (JSONB)
     │     • denormalized query columns (stock_type, complexity_*, etc.)
     │     • Phase B columns (flip/multi-axis flags, hole types, machining classes)
     └── ModelFeature[] (cad_worker)    ← raw detected features
           • type, dimensions, depth, diameter, axis, confidence

DATA FLOW (CAD Worker Pipeline)
================================
  1. worker.py: extract geometry → GeometryResult → save_geometry_result()
     → Creates ModelGeometry row with basic metrics

  2. worker.py: detect features → FeatureResult[] → save_features()
     → Creates ModelFeature rows linked to model_id

  3. worker.py: intelligence orchestrator → ManufacturingGeometryReport
     → save_intelligence_report() → Updates ModelGeometry with:
       - manufacturing_intelligence_report (full JSONB)
       - intelligence_ready = True
       - Denormalized columns for efficient queries

DENORMALIZED COLUMNS RATIONALE
===============================
The JSONB report stores the complete intelligence data. However, querying
JSONB for filtering/sorting is expensive. We denormalize frequently-queried
fields into dedicated columns:

  Phase A columns:
    • stock_type         → for RFQ filtering ("show all BAR stock parts")
    • complexity_value   → for RFQ sorting ("most complex first")
    • complexity_level   → for dashboard ("X HIGH parts pending")
    • intelligence_partial → for quality monitoring ("partial reports")
    • intelligence_feature_count → for quick stats
    • intelligence_warning_count → for DFM flags
    • intelligence_engine_status → for debugging pipeline failures

  Phase B columns:
    • intelligence_chamfer_count → operation count estimation
    • intelligence_fillet_count  → finishing pass estimation
    • intelligence_flip_required → setup planning ("needs 2-setup")
    • intelligence_multi_axis_required → machine routing ("needs 5-axis")
    • intelligence_hole_types    → tool set planning (JSON breakdown)
    • intelligence_machining_classes → operation grouping (JSON breakdown)

These are populated by db_service.save_intelligence_report() at the same
time as the JSONB — single transaction, no sync issues.
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
    """
    Deterministic geometry metrics + manufacturing intelligence for a CAD model.

    One-to-one relationship with CADModel via model_id FK.
    Created by save_geometry_result(), updated by save_intelligence_report().
    """
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

    # ── Basic Geometry (populated by save_geometry_result) ──────────────

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

    # ── Phase A Intelligence (populated by save_intelligence_report) ────

    # Full ManufacturingGeometryReport as JSONB
    # Contains: geometry_summary, topology_graph, features,
    # stock_recommendation, datum_candidates, manufacturability_analysis,
    # complexity_score
    manufacturing_intelligence_report: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        comment="Full ManufacturingGeometryReport (Phase A intelligence)",
    )

    # Pipeline status flags
    intelligence_ready: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="True when intelligence report is available",
    )
    intelligence_partial: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="True if some intelligence engines failed (partial report)",
    )

    # ── Denormalized Query Columns ──────────────────────────────────────
    # Extracted from the JSONB at write time for efficient SQL queries.
    # These avoid expensive JSONB path queries like:
    #   WHERE manufacturing_intelligence_report->>'stock_recommendation'->>'type' = 'BAR'

    # Stock recommendation type: PLATE, BAR, or BLOCK
    stock_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None, index=True,
        comment="Denormalized: stock type (PLATE/BAR/BLOCK)",
    )

    # Complexity score value: 0.0 to 1.0 (normalized)
    complexity_value: Mapped[float | None] = mapped_column(
        Float, nullable=True, default=None,
        comment="Denormalized: complexity score (0.0-1.0)",
    )

    # Complexity level: LOW, MEDIUM, HIGH
    complexity_level: Mapped[str | None] = mapped_column(
        String(10), nullable=True, default=None, index=True,
        comment="Denormalized: complexity level (LOW/MEDIUM/HIGH)",
    )

    # Feature count from intelligence (not from model_features table)
    intelligence_feature_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Spatially-mapped feature count from intelligence pipeline",
    )

    # DFM warning count
    intelligence_warning_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Manufacturability warning count",
    )

    # Engine-by-engine status: {"geometry_summary": "OK", "topology_graph": "FAILED: ..."}
    intelligence_engine_status: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=None,
        comment="Per-engine pipeline status for debugging",
    )

    # ── Phase B Denormalized Columns ────────────────────────────────────
    # These enable Phase B planning queries without JSONB parsing.

    # Chamfer and fillet counts for operation count estimation
    intelligence_chamfer_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Number of detected chamfer features",
    )
    intelligence_fillet_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="Number of detected fillet features",
    )

    # Setup planning flags — critical for quoting and scheduling
    # "Show all parts requiring flip" → WHERE intelligence_flip_required = TRUE
    intelligence_flip_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True,
        comment="True if any feature requires part flip (multi-setup)",
    )

    # Machine routing — determines which CNC machines can produce this part
    # "Show all 5-axis parts" → WHERE intelligence_multi_axis_required = TRUE
    intelligence_multi_axis_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True,
        comment="True if any feature requires 4-axis or 5-axis machining",
    )

    # Hole subtype breakdown for tool set planning
    # e.g., {"THROUGH": 3, "BLIND": 2, "COUNTERBORE": 1}
    intelligence_hole_types: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=None,
        comment="Hole subtype counts: {THROUGH: N, BLIND: N, ...}",
    )

    # Machining class breakdown for operation grouping
    # e.g., {"DRILL": 5, "ROUGH": 2, "CHAMFER": 3, "FINISH": 1}
    intelligence_machining_classes: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=None,
        comment="Machining class counts: {DRILL: N, ROUGH: N, ...}",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<ModelGeometry id={self.id} model_id={self.model_id} "
            f"type={self.geometry_type} feature_ready={self.feature_ready} "
            f"intel_ready={self.intelligence_ready} "
            f"partial={self.intelligence_partial} "
            f"flip={self.intelligence_flip_required} "
            f"multi_axis={self.intelligence_multi_axis_required}>"
        )


# ── ModelFeature ──────────────────────────────────────────────────────────────

class ModelFeature(Base):
    """
    A single detected machining feature on a CAD model.

    Feature types: HOLE, POCKET, SLOT, TURN_PROFILE
    Only created for BREP models (feature_ready == True).

    Created by save_features() during worker processing.
    Many-to-one with CADModel via model_id FK.
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
            "HOLE", "POCKET", "SLOT", "TURN_PROFILE", "CHAMFER", "FILLET",
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
