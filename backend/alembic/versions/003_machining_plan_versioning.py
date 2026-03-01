"""add versioning columns to machining_plans

Revision ID: 003_machining_plan_versioning
Revises: 002_phase_b_columns
Create Date: 2026-03-01

Adds Phase B hybrid co-planner columns to machining_plans table:
  - previous_version_id  (VARCHAR 36, nullable)  — back-link to parent version
  - modification_reason  (TEXT, nullable)         — why this version was created
  - approval_status      (VARCHAR 20, NOT NULL)   — DRAFT / PENDING_REVIEW / APPROVED / REJECTED
"""

from alembic import op
import sqlalchemy as sa


revision = "003_machining_plan_versioning"
down_revision = "002_phase_b_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add versioning + approval_status columns to machining_plans."""

    op.add_column(
        "machining_plans",
        sa.Column(
            "previous_version_id",
            sa.String(36),
            nullable=True,
            comment="ID of the plan this version was derived from (NULL for v1)",
        ),
    )

    op.add_column(
        "machining_plans",
        sa.Column(
            "modification_reason",
            sa.Text(),
            nullable=True,
            comment="Why this version was created (e.g. 'User confirmed tool change')",
        ),
    )

    op.add_column(
        "machining_plans",
        sa.Column(
            "approval_status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
            comment="DRAFT | PENDING_REVIEW | APPROVED | REJECTED",
        ),
    )

    # Index for quick "find parent" lookups
    op.create_index(
        "ix_machining_plans_previous_version_id",
        "machining_plans",
        ["previous_version_id"],
    )

    # Index for approval status filtering
    op.create_index(
        "ix_machining_plans_approval_status",
        "machining_plans",
        ["approval_status"],
    )


def downgrade() -> None:
    """Remove versioning columns."""
    op.drop_index("ix_machining_plans_approval_status", table_name="machining_plans")
    op.drop_index("ix_machining_plans_previous_version_id", table_name="machining_plans")
    op.drop_column("machining_plans", "approval_status")
    op.drop_column("machining_plans", "modification_reason")
    op.drop_column("machining_plans", "previous_version_id")
