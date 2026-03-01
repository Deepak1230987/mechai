"""
Feedback Service — structured diff calculation and plan edit orchestration.

Responsibilities:
    • calculate_diff()  — structured JSON diff between two plan versions
    • apply_edit()      — create new immutable version + PlanFeedback record
    • approve_plan()    — validate then set approved=True
    • get_latest_plan() — fetch highest-version plan for a model

Diff must never block the request.  All edits are immutable (new row, never update-in-place).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_service.models import MachiningPlan, PlanFeedback
from ai_service.planning.plan_validator import PlanValidationError

logger = logging.getLogger(__name__)


# ── Structured Diff ───────────────────────────────────────────────────────────

def calculate_diff(original_plan: dict, edited_plan: dict) -> dict:
    """
    Compute a structured diff between two plan versions.

    Returns:
        {
            "operations_added":   [op_ids new in edited],
            "operations_removed": [op_ids removed from original],
            "operations_changed": [op_ids present in both but modified],
            "tools_changed":      [tool_ids that differ],
            "order_changed":      bool,
            "setups_changed":     bool,
            "time_delta":         float (edited - original seconds),
        }
    """
    orig_ops = {op["id"]: op for op in original_plan.get("operations", [])}
    edit_ops = {op["id"]: op for op in edited_plan.get("operations", [])}

    orig_ids = set(orig_ops.keys())
    edit_ids = set(edit_ops.keys())

    operations_added = sorted(edit_ids - orig_ids)
    operations_removed = sorted(orig_ids - edit_ids)

    operations_changed: list[str] = []
    for oid in sorted(orig_ids & edit_ids):
        if orig_ops[oid] != edit_ops[oid]:
            operations_changed.append(oid)

    # ── Tools diff ────────────────────────────────────────────────────────
    orig_tools = {t["id"]: t for t in original_plan.get("tools", [])}
    edit_tools = {t["id"]: t for t in edited_plan.get("tools", [])}
    all_tool_ids = set(orig_tools.keys()) | set(edit_tools.keys())
    tools_changed = sorted(
        tid for tid in all_tool_ids
        if orig_tools.get(tid) != edit_tools.get(tid)
    )

    # ── Operation order diff ──────────────────────────────────────────────
    orig_order = [op["id"] for op in original_plan.get("operations", [])]
    edit_order = [op["id"] for op in edited_plan.get("operations", [])]
    order_changed = orig_order != edit_order

    # ── Setups diff ───────────────────────────────────────────────────────
    orig_setups = original_plan.get("setups", [])
    edit_setups = edited_plan.get("setups", [])
    setups_changed = orig_setups != edit_setups

    # ── Time delta ────────────────────────────────────────────────────────
    orig_time = original_plan.get("estimated_time", 0)
    edit_time = edited_plan.get("estimated_time", 0)

    return {
        "operations_added": operations_added,
        "operations_removed": operations_removed,
        "operations_changed": operations_changed,
        "tools_changed": tools_changed,
        "order_changed": order_changed,
        "setups_changed": setups_changed,
        "time_delta": round(edit_time - orig_time, 2),
    }


# ── Apply Edit (create new version) ──────────────────────────────────────────

async def apply_edit(
    plan_id: str,
    edited_plan_data: dict,
    edited_by: str,
    session: AsyncSession,
) -> MachiningPlan:
    """
    Create a new immutable plan version from a human edit.

    Steps:
        1. Fetch original plan (by plan_id)
        2. Validate edited plan structure
        3. Calculate structured diff
        4. Compute next version number
        5. Insert new MachiningPlan row (approved=False)
        6. Insert PlanFeedback record
        7. Return new plan row

    Raises HTTPException on invalid input or missing plan.
    """

    # ── 1. Fetch original ─────────────────────────────────────────────────
    original = await session.get(MachiningPlan, plan_id)
    if original is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )

    original_data: dict = original.plan_data

    # ── 2. Structural validation of edited plan ──────────────────────────
    #   We validate using the same PlanValidator, but without requiring
    #   the full feature list (user edits may not have features context).
    #   Minimal check: required keys + internal consistency.
    for key in ("setups", "operations", "tools", "estimated_time"):
        if key not in edited_plan_data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Edited plan missing required field: {key}",
            )

    # ── 3. Calculate diff ────────────────────────────────────────────────
    diff = calculate_diff(original_data, edited_plan_data)

    # ── 4. Compute next version ──────────────────────────────────────────
    max_version_result = await session.execute(
        select(func.coalesce(func.max(MachiningPlan.version), 0)).where(
            MachiningPlan.model_id == original.model_id
        )
    )
    next_version: int = max_version_result.scalar_one() + 1

    # ── 5. Overlay immutable fields onto edited plan ─────────────────────
    edited_plan_data["model_id"] = original.model_id
    edited_plan_data["material"] = original.material
    edited_plan_data["machine_type"] = original.machine_type
    edited_plan_data["version"] = next_version
    edited_plan_data["approved"] = False

    # ── 6. Insert new plan row ───────────────────────────────────────────
    new_plan_id = str(uuid.uuid4())
    new_plan = MachiningPlan(
        id=new_plan_id,
        model_id=original.model_id,
        material=original.material,
        machine_type=original.machine_type,
        plan_data=edited_plan_data,
        estimated_time=edited_plan_data.get("estimated_time", 0),
        version=next_version,
        approved=False,
    )
    session.add(new_plan)

    # ── 7. Insert feedback record ────────────────────────────────────────
    feedback = PlanFeedback(
        id=str(uuid.uuid4()),
        plan_id=plan_id,
        new_plan_id=new_plan_id,
        original_plan=original_data,
        edited_plan=edited_plan_data,
        diff=diff,
        edited_by=edited_by,
    )
    session.add(feedback)

    logger.info(
        "Plan edit: model=%s v%d→v%d by=%s | ops +%d -%d ~%d | tools ~%d",
        original.model_id,
        original.version,
        next_version,
        edited_by,
        len(diff["operations_added"]),
        len(diff["operations_removed"]),
        len(diff["operations_changed"]),
        len(diff["tools_changed"]),
    )

    return new_plan


# ── Approve Plan ──────────────────────────────────────────────────────────────

async def approve_plan(
    plan_id: str,
    approved_by: str,
    session: AsyncSession,
) -> MachiningPlan:
    """
    Validate and approve a plan.

    Steps:
        1. Fetch plan
        2. Re-validate plan_data (must still be structurally sound)
        3. Set approved=True, approved_by, approved_at
        4. Return updated plan

    Raises HTTPException on invalid plan or already-approved plan.
    """
    plan = await session.get(MachiningPlan, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )

    if plan.approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Plan {plan_id} v{plan.version} is already approved",
        )

    # ── Re-validate plan data ────────────────────────────────────────────
    # Build a MachiningPlanResponse + minimal PlanningContext for validation.
    from ai_service.schemas.machining_plan import MachiningPlanResponse
    from ai_service.schemas.planning_context import PlanningContext, FeatureContext
    from ai_service.planning.plan_validator import validate_final_plan

    plan_data = plan.plan_data
    plan_response = MachiningPlanResponse(**plan_data)

    # Build minimal PlanningContext from the operations' feature_ids
    feature_stubs = [
        FeatureContext(id=op["feature_id"], type="UNKNOWN", confidence=1.0)
        for op in plan_data.get("operations", [])
    ]
    # Deduplicate by feature id
    seen_ids: set[str] = set()
    unique_features: list[FeatureContext] = []
    for f in feature_stubs:
        if f.id not in seen_ids:
            seen_ids.add(f.id)
            unique_features.append(f)

    context = PlanningContext(
        model_id=plan.model_id,
        material=plan.material,
        machine_type=plan.machine_type,
        features=unique_features,
    )

    vr = validate_final_plan(plan_response, context)
    if not vr.valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Plan failed validation, cannot approve: {vr.errors}",
        )

    # ── Set approval fields ──────────────────────────────────────────────
    plan.approved = True
    plan.approved_by = approved_by
    plan.approved_at = datetime.now(timezone.utc)

    logger.info(
        "Plan approved: id=%s model=%s v%d by=%s",
        plan_id, plan.model_id, plan.version, approved_by,
    )

    return plan


# ── Get Latest Plan ──────────────────────────────────────────────────────────

async def get_latest_plan(
    model_id: str,
    session: AsyncSession,
) -> MachiningPlan:
    """
    Fetch the latest (highest version) plan for a model.

    Raises HTTPException if no plans exist.
    """
    result = await session.execute(
        select(MachiningPlan)
        .where(MachiningPlan.model_id == model_id)
        .order_by(MachiningPlan.version.desc())
        .limit(1)
    )
    plan = result.scalars().first()

    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No plans found for model {model_id}",
        )

    return plan
