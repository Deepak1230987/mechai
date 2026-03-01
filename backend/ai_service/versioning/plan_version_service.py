"""
Plan Version Service — persistence and version management for machining plans.

Responsibilities:
  • Save new plans (version 1)
  • Create new versions from confirmed modifications
  • Retrieve version history for a model
  • Retrieve a specific plan by ID or latest for a model
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ai_service.models import MachiningPlan
from ai_service.schemas.machining_plan import MachiningPlanResponse

logger = logging.getLogger("ai_service.versioning.plan_version_service")


class PlanVersionService:
    """Manages version lifecycle for machining plans in the DB."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Create ────────────────────────────────────────────────────────────

    async def save_initial_plan(
        self,
        plan: MachiningPlanResponse,
        process_summary: str | None = None,
    ) -> MachiningPlan:
        """
        Persist the first version of a plan (v1).

        Returns the ORM instance with generated id.
        """
        plan_id = str(uuid.uuid4())

        # Stamp the plan response with the DB id and version
        plan.plan_id = plan_id
        plan.version = 1
        plan.approval_status = "DRAFT"

        row = MachiningPlan(
            id=plan_id,
            model_id=plan.model_id,
            material=plan.material,
            machine_type=plan.machine_type,
            plan_data=plan.model_dump(mode="json"),
            estimated_time=plan.estimated_time,
            version=1,
            approved=False,
            approval_status="DRAFT",
            process_summary=process_summary,
        )
        self.session.add(row)
        await self.session.flush()

        logger.info(
            "Saved initial plan %s for model %s (v1, %.1fs)",
            plan_id, plan.model_id, plan.estimated_time,
        )
        return row

    async def save_new_version(
        self,
        previous_plan_id: str,
        plan: MachiningPlanResponse,
        modification_reason: str,
        process_summary: str | None = None,
    ) -> MachiningPlan:
        """
        Create a new version from a confirmed modification.

        Increments version number from the previous plan.
        """
        # Fetch previous to get version number
        prev = await self.session.get(MachiningPlan, previous_plan_id)
        if prev is None:
            raise ValueError(f"Previous plan {previous_plan_id} not found")

        new_version = prev.version + 1
        new_id = str(uuid.uuid4())

        plan.plan_id = new_id
        plan.version = new_version
        plan.approval_status = "PENDING_REVIEW"

        row = MachiningPlan(
            id=new_id,
            model_id=plan.model_id,
            material=plan.material,
            machine_type=plan.machine_type,
            plan_data=plan.model_dump(mode="json"),
            estimated_time=plan.estimated_time,
            version=new_version,
            approved=False,
            approval_status="PENDING_REVIEW",
            previous_version_id=previous_plan_id,
            modification_reason=modification_reason,
            process_summary=process_summary,
        )
        self.session.add(row)
        await self.session.flush()

        logger.info(
            "Saved plan %s v%d (prev=%s, reason=%s)",
            new_id, new_version, previous_plan_id, modification_reason[:80],
        )
        return row

    # ── Read ──────────────────────────────────────────────────────────────

    async def get_plan(self, plan_id: str) -> MachiningPlan | None:
        """Fetch a single plan by its ID."""
        return await self.session.get(MachiningPlan, plan_id)

    async def get_latest_plan(self, model_id: str) -> MachiningPlan | None:
        """Fetch the most recent plan version for a model."""
        stmt = (
            select(MachiningPlan)
            .where(MachiningPlan.model_id == model_id)
            .order_by(desc(MachiningPlan.version))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_version_history(
        self,
        model_id: str,
        limit: int = 20,
    ) -> list[dict]:
        """
        Return version history for a model (newest first).

        Returns lightweight dicts (no full plan_data) for listing.
        """
        stmt = (
            select(
                MachiningPlan.id,
                MachiningPlan.version,
                MachiningPlan.estimated_time,
                MachiningPlan.approved,
                MachiningPlan.approval_status,
                MachiningPlan.previous_version_id,
                MachiningPlan.modification_reason,
                MachiningPlan.created_at,
            )
            .where(MachiningPlan.model_id == model_id)
            .order_by(desc(MachiningPlan.version))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            {
                "plan_id": r.id,
                "version": r.version,
                "estimated_time": r.estimated_time,
                "approved": r.approved,
                "approval_status": r.approval_status,
                "previous_version_id": r.previous_version_id,
                "modification_reason": r.modification_reason,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    # ── Update status ─────────────────────────────────────────────────────

    async def approve_plan(
        self,
        plan_id: str,
        user_id: str,
    ) -> MachiningPlan | None:
        """Mark a plan as approved."""
        row = await self.session.get(MachiningPlan, plan_id)
        if row is None:
            return None
        row.approved = True
        row.approved_by = user_id
        row.approved_at = datetime.now(timezone.utc)
        row.approval_status = "APPROVED"
        await self.session.flush()
        logger.info("Plan %s approved by %s", plan_id, user_id)
        return row

    async def reject_plan(
        self,
        plan_id: str,
    ) -> MachiningPlan | None:
        """Mark a plan as rejected."""
        row = await self.session.get(MachiningPlan, plan_id)
        if row is None:
            return None
        row.approval_status = "REJECTED"
        await self.session.flush()
        logger.info("Plan %s rejected", plan_id)
        return row
