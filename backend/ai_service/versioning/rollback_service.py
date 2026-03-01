"""
Rollback Service — restore a previous plan version as a new immutable entry.

Rules:
  • Rollback NEVER deletes history.
  • Rollback creates a NEW version (is_rollback=True).
  • Rollback preserves traceability via parent_version_id.
  • Rollback does NOT re-trigger LLM automatically.
  • Rollback does NOT bypass validation schema.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ai_service.models import MachiningPlan
from ai_service.schemas.machining_plan import MachiningPlanResponse

logger = logging.getLogger("ai_service.versioning.rollback_service")


class RollbackService:
    """Handles plan version rollbacks."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def rollback_to_version(
        self,
        model_id: str,
        target_version_number: int,
        reason: str,
    ) -> MachiningPlan:
        """
        Restore a previous plan version by cloning it as a new version.

        Workflow:
          1. Fetch the target version for the given model.
          2. Fetch the current latest version to compute next version number.
          3. Clone plan JSON from target.
          4. Store as new version with is_rollback=True, parent_version_id
             pointing to the target.
          5. Return the new plan row.

        Raises:
            ValueError: if target version or model not found.
        """
        # ── 1. Fetch target version ──────────────────────────────────────────
        stmt = (
            select(MachiningPlan)
            .where(
                MachiningPlan.model_id == model_id,
                MachiningPlan.version == target_version_number,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        target = result.scalar_one_or_none()

        if target is None:
            raise ValueError(
                f"Version {target_version_number} not found for model {model_id}"
            )

        # ── 2. Fetch current latest version number ──────────────────────────
        latest_stmt = (
            select(MachiningPlan.version)
            .where(MachiningPlan.model_id == model_id)
            .order_by(desc(MachiningPlan.version))
            .limit(1)
        )
        latest_result = await self.session.execute(latest_stmt)
        latest_version = latest_result.scalar_one_or_none() or 0
        new_version = latest_version + 1

        # ── 3. Clone plan JSON ───────────────────────────────────────────────
        cloned_plan_data = dict(target.plan_data)  # shallow copy of JSONB

        # Update version metadata in plan_data
        new_id = str(uuid.uuid4())
        cloned_plan_data["version"] = new_version
        cloned_plan_data["plan_id"] = new_id
        cloned_plan_data["approved"] = False
        cloned_plan_data["approval_status"] = "DRAFT"
        cloned_plan_data["approved_by"] = None
        cloned_plan_data["approved_at"] = None
        cloned_plan_data["is_rollback"] = True
        cloned_plan_data["parent_version_id"] = target.id

        # ── 4. Store as new version ──────────────────────────────────────────
        row = MachiningPlan(
            id=new_id,
            model_id=model_id,
            material=target.material,
            machine_type=target.machine_type,
            plan_data=cloned_plan_data,
            estimated_time=target.estimated_time,
            version=new_version,
            approved=False,
            approval_status="DRAFT",
            previous_version_id=target.id,   # links to the version we rolled back to
            parent_version_id=target.id,     # explicit rollback parent
            modification_reason=reason,
            is_rollback=True,
        )
        self.session.add(row)
        await self.session.flush()

        logger.info(
            "Rolled back model %s to v%d → created v%d (plan_id=%s, reason=%s)",
            model_id,
            target_version_number,
            new_version,
            new_id,
            reason[:80],
        )
        return row

    async def get_version(
        self,
        model_id: str,
        version_number: int,
    ) -> MachiningPlan | None:
        """Retrieve a specific version for a model."""
        stmt = (
            select(MachiningPlan)
            .where(
                MachiningPlan.model_id == model_id,
                MachiningPlan.version == version_number,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_versions(
        self,
        model_id: str,
        limit: int = 50,
    ) -> list[MachiningPlan]:
        """List all versions for a model (newest first)."""
        stmt = (
            select(MachiningPlan)
            .where(MachiningPlan.model_id == model_id)
            .order_by(desc(MachiningPlan.version))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
