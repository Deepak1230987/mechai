"""
Consent Manager — enforces human-in-the-loop for all plan modifications.

Rules:
  • No silent modification of any plan
  • Explicit "CONFIRM" required before applying changes
  • Every confirmed change creates a new version
  • Version history is stored with modification reason
  • Pending proposals expire (not persisted to DB until confirmed)

State is held per-session (plan_id → pending proposal).
In production, this would use Redis or a DB table for TTL/persistence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ai_service.schemas.llm_diff_schema import LLMDiff
from ai_service.schemas.machining_plan import MachiningPlanResponse
from ai_service.schemas.planning_context import PlanningContext
from ai_service.planning.plan_merger import merge_base_and_llm

logger = logging.getLogger("ai_service.chat.consent_manager")


# ── In-memory pending proposals (per plan_id) ────────────────────────────────
# In production: use Redis with TTL or a DB pending_proposals table.

_pending_proposals: dict[str, dict[str, Any]] = {}


class ConsentManager:
    """Manages pending plan modification proposals and consent flow."""

    @staticmethod
    def store_proposal(
        plan_id: str,
        diff: LLMDiff,
        preview_plan: MachiningPlanResponse,
        context: PlanningContext,
        summary: str,
    ) -> str:
        """
        Store a pending proposal for user review.

        Returns:
            Proposal key for confirmation/rejection.
        """
        proposal_key = f"{plan_id}:pending"
        _pending_proposals[proposal_key] = {
            "plan_id": plan_id,
            "diff": diff,
            "preview_plan": preview_plan,
            "context": context,
            "summary": summary,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(
            "Stored pending proposal for plan %s (%d changes)",
            plan_id, diff.change_count,
        )
        return proposal_key

    @staticmethod
    def has_pending(plan_id: str) -> bool:
        """Check if there's a pending proposal for this plan."""
        return f"{plan_id}:pending" in _pending_proposals

    @staticmethod
    def get_pending(plan_id: str) -> dict[str, Any] | None:
        """Retrieve the pending proposal for confirmation."""
        return _pending_proposals.get(f"{plan_id}:pending")

    @staticmethod
    def confirm(plan_id: str) -> MachiningPlanResponse | None:
        """
        Confirm and apply the pending proposal.

        Returns:
            The merged plan to be persisted, or None if no pending proposal.
        """
        key = f"{plan_id}:pending"
        proposal = _pending_proposals.pop(key, None)
        if proposal is None:
            logger.warning("No pending proposal to confirm for plan %s", plan_id)
            return None

        preview = proposal["preview_plan"]
        logger.info(
            "Proposal confirmed for plan %s — %d changes applied",
            plan_id, proposal["diff"].change_count,
        )
        return preview

    @staticmethod
    def reject(plan_id: str) -> bool:
        """
        Reject and discard the pending proposal.

        Returns:
            True if a proposal was discarded, False if none existed.
        """
        key = f"{plan_id}:pending"
        discarded = _pending_proposals.pop(key, None) is not None
        if discarded:
            logger.info("Proposal rejected for plan %s", plan_id)
        else:
            logger.debug("No pending proposal to reject for plan %s", plan_id)
        return discarded

    @staticmethod
    def clear_all() -> int:
        """Clear all pending proposals. Returns count cleared."""
        count = len(_pending_proposals)
        _pending_proposals.clear()
        return count
