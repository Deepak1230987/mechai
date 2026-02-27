"""add intelligence denormalized columns to model_geometry

Revision ID: 001_intelligence_columns
Revises: (initial)
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


revision = "001_intelligence_columns"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add Phase A intelligence columns to model_geometry table.

    These columns support the hardened Manufacturing Geometry Intelligence
    Engine. The schema changes are:

    Existing columns (already in model):
      - manufacturing_intelligence_report (JSON, nullable)
      - intelligence_ready (BOOLEAN, default False)

    New columns:
      - intelligence_partial (BOOLEAN) — True if some engines failed
      - stock_type (VARCHAR 20, indexed) — denormalized stock recommendation
      - complexity_value (FLOAT) — denormalized complexity score
      - complexity_level (VARCHAR 10, indexed) — denormalized complexity tier
      - intelligence_feature_count (INTEGER) — spatially-mapped feature count
      - intelligence_warning_count (INTEGER) — DFM warning count
      - intelligence_engine_status (JSON) — per-engine pipeline status

    All new columns have safe defaults (False, 0, NULL) so existing rows
    are unaffected. No data migration needed.
    """
    # ── New columns ─────────────────────────────────────────────────────
    op.add_column(
        "model_geometry",
        sa.Column(
            "intelligence_partial",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if some intelligence engines failed (partial report)",
        ),
    )
    op.add_column(
        "model_geometry",
        sa.Column(
            "stock_type",
            sa.String(20),
            nullable=True,
            comment="Denormalized: stock type (PLATE/BAR/BLOCK)",
        ),
    )
    op.add_column(
        "model_geometry",
        sa.Column(
            "complexity_value",
            sa.Float(),
            nullable=True,
            comment="Denormalized: complexity score (0.0-1.0)",
        ),
    )
    op.add_column(
        "model_geometry",
        sa.Column(
            "complexity_level",
            sa.String(10),
            nullable=True,
            comment="Denormalized: complexity level (LOW/MEDIUM/HIGH)",
        ),
    )
    op.add_column(
        "model_geometry",
        sa.Column(
            "intelligence_feature_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Spatially-mapped feature count from intelligence pipeline",
        ),
    )
    op.add_column(
        "model_geometry",
        sa.Column(
            "intelligence_warning_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Manufacturability warning count",
        ),
    )
    op.add_column(
        "model_geometry",
        sa.Column(
            "intelligence_engine_status",
            JSON(),
            nullable=True,
            comment="Per-engine pipeline status for debugging",
        ),
    )

    # ── Indexes for query performance ───────────────────────────────────
    # stock_type: WHERE stock_type = 'BAR' for RFQ filtering
    op.create_index(
        "ix_model_geometry_stock_type",
        "model_geometry",
        ["stock_type"],
    )
    # complexity_level: WHERE complexity_level = 'HIGH' for dashboards
    op.create_index(
        "ix_model_geometry_complexity_level",
        "model_geometry",
        ["complexity_level"],
    )


def downgrade() -> None:
    """Remove intelligence denormalized columns."""
    op.drop_index("ix_model_geometry_complexity_level", table_name="model_geometry")
    op.drop_index("ix_model_geometry_stock_type", table_name="model_geometry")
    op.drop_column("model_geometry", "intelligence_engine_status")
    op.drop_column("model_geometry", "intelligence_warning_count")
    op.drop_column("model_geometry", "intelligence_feature_count")
    op.drop_column("model_geometry", "complexity_level")
    op.drop_column("model_geometry", "complexity_value")
    op.drop_column("model_geometry", "stock_type")
    op.drop_column("model_geometry", "intelligence_partial")
