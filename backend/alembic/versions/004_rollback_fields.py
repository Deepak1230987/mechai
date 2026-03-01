"""Add rollback columns to machining_plans

Revision ID: 004_rollback_fields
Revises: 003_machining_plan_versioning
Create Date: 2026-03-01

Adds:
  - parent_version_id  (VARCHAR 36, nullable) — rollback source version
  - is_rollback        (BOOLEAN, NOT NULL, default FALSE)
  - index on parent_version_id
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "004_rollback_fields"
down_revision = "003_machining_plan_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "machining_plans",
        sa.Column(
            "parent_version_id",
            sa.String(36),
            nullable=True,
            comment="ID of the version this was rolled back from (NULL for non-rollback)",
        ),
    )
    op.add_column(
        "machining_plans",
        sa.Column(
            "is_rollback",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True if this version was created via rollback",
        ),
    )
    op.create_index(
        "ix_machining_plans_parent_version_id",
        "machining_plans",
        ["parent_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_machining_plans_parent_version_id", table_name="machining_plans")
    op.drop_column("machining_plans", "is_rollback")
    op.drop_column("machining_plans", "parent_version_id")
