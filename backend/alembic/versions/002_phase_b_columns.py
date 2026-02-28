"""add Phase B intelligence columns to model_geometry

Revision ID: 002_phase_b_columns
Revises: 001_intelligence_columns
Create Date: 2026-02-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


revision = "002_phase_b_columns"
down_revision = "001_intelligence_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Add Phase B intelligence columns to model_geometry table.

    These columns support the Phase B readiness upgrade for the
    AI Process Planning Brain. They enable efficient SQL queries for:
      - Setup planning (flip/multi-axis flags)
      - Tool set planning (hole subtype breakdown)
      - Operation grouping (machining class breakdown)
      - Operation count estimation (chamfer/fillet counts)

    All new columns have safe defaults so existing rows are unaffected.
    """
    # ── Chamfer and fillet counts ───────────────────────────────────────
    op.add_column(
        "model_geometry",
        sa.Column(
            "intelligence_chamfer_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Number of detected chamfer features",
        ),
    )
    op.add_column(
        "model_geometry",
        sa.Column(
            "intelligence_fillet_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Number of detected fillet features",
        ),
    )

    # ── Setup planning flags ───────────────────────────────────────────
    op.add_column(
        "model_geometry",
        sa.Column(
            "intelligence_flip_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if any feature requires part flip (multi-setup)",
        ),
    )
    op.add_column(
        "model_geometry",
        sa.Column(
            "intelligence_multi_axis_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if any feature requires 4-axis or 5-axis machining",
        ),
    )

    # ── JSON breakdown columns ──────────────────────────────────────────
    op.add_column(
        "model_geometry",
        sa.Column(
            "intelligence_hole_types",
            JSON(),
            nullable=True,
            comment="Hole subtype counts: {THROUGH: N, BLIND: N, ...}",
        ),
    )
    op.add_column(
        "model_geometry",
        sa.Column(
            "intelligence_machining_classes",
            JSON(),
            nullable=True,
            comment="Machining class counts: {DRILL: N, ROUGH: N, ...}",
        ),
    )

    # ── Indexes for query performance ───────────────────────────────────
    # flip_required: WHERE intelligence_flip_required = TRUE
    # for quote estimation ("parts needing 2+ setups")
    op.create_index(
        "ix_model_geometry_flip_required",
        "model_geometry",
        ["intelligence_flip_required"],
    )
    # multi_axis_required: WHERE intelligence_multi_axis_required = TRUE
    # for machine routing ("parts needing 5-axis")
    op.create_index(
        "ix_model_geometry_multi_axis_required",
        "model_geometry",
        ["intelligence_multi_axis_required"],
    )

    # ── Update feature_type_enum to include CHAMFER and FILLET ──────────
    # PostgreSQL enums must be altered with ALTER TYPE ... ADD VALUE
    # This is idempotent — Postgres ignores ADD VALUE if it already exists
    # (when using IF NOT EXISTS)
    op.execute("ALTER TYPE feature_type_enum ADD VALUE IF NOT EXISTS 'CHAMFER'")
    op.execute("ALTER TYPE feature_type_enum ADD VALUE IF NOT EXISTS 'FILLET'")


def downgrade() -> None:
    """Remove Phase B intelligence columns."""
    op.drop_index("ix_model_geometry_multi_axis_required", table_name="model_geometry")
    op.drop_index("ix_model_geometry_flip_required", table_name="model_geometry")
    op.drop_column("model_geometry", "intelligence_machining_classes")
    op.drop_column("model_geometry", "intelligence_hole_types")
    op.drop_column("model_geometry", "intelligence_multi_axis_required")
    op.drop_column("model_geometry", "intelligence_flip_required")
    op.drop_column("model_geometry", "intelligence_fillet_count")
    op.drop_column("model_geometry", "intelligence_chamfer_count")
    # Note: PostgreSQL does not support removing values from enums.
    # CHAMFER and FILLET will remain in feature_type_enum after downgrade.
