"""
Refinement Engine — conversational plan modification via structured LLM diff.

Workflow:
  1. Parse user intent (modification request)
  2. Generate LLM structured diff (same LLMDiff schema as co-planner)
  3. Validate diff against current plan
  4. Present summary to user (DO NOT apply yet)
  5. Wait for explicit confirmation via consent_manager
  6. On confirm: apply via merger, increment version

Never silently modifies a plan. Every change goes through consent flow.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from ai_service.schemas.llm_diff_schema import LLMDiff
from ai_service.schemas.machining_plan import MachiningPlanResponse
from ai_service.schemas.planning_context import PlanningContext
from ai_service.planning.plan_validator import validate_llm_diff, ValidationResult
from ai_service.planning.plan_merger import merge_base_and_llm
from ai_service.services.langchain_pipeline import _build_llm

logger = logging.getLogger("ai_service.chat.refinement_engine")


_REFINEMENT_SYSTEM = """\
You are a CNC process planning optimizer. The user wants to modify their
machining plan. Produce a structured diff (same format as the co-planner).

Output a JSON object matching this schema:
{{
  "operation_reorders": [...],
  "tool_changes": [...],
  "parameter_changes": [...],
  "setup_modifications": [...],
  "operation_additions": [...],
  "justification": "<reasoning for changes>",
  "estimated_time_change": <float, negative=faster>,
  "confidence": <float 0-1>
}}

STRICT RULES:
1. Only reference existing feature IDs and operation IDs.
2. Do NOT remove safety operations.
3. Do NOT create new features.
4. If the request is impossible, return empty lists with justification explaining why.
5. Output ONLY JSON.

Material: {material}
Machine type: {machine_type}
"""

_REFINEMENT_USER = """\
Current plan:
{plan_json}

Features:
{features_json}

User instruction: {user_message}

Generate the structured diff.
"""


async def generate_refinement_diff(
    user_message: str,
    plan: MachiningPlanResponse,
    context: PlanningContext,
) -> dict[str, Any]:
    """
    Generate a validated diff from user's chat instruction.

    Returns:
        {
            "diff": LLMDiff,
            "validation": ValidationResult,
            "preview_plan": MachiningPlanResponse | None,
            "summary": str,
        }
    """
    llm = _build_llm()
    if llm is None:
        return {
            "diff": LLMDiff(justification="LLM unavailable"),
            "validation": ValidationResult(valid=False, errors=["LLM not configured"]),
            "preview_plan": None,
            "summary": "LLM provider is not configured. Cannot process plan modifications.",
        }

    # ── 1. Generate diff via LLM ─────────────────────────────────────────
    diff = await _call_refinement_llm(llm, user_message, plan, context)
    if diff is None:
        return {
            "diff": LLMDiff(justification="LLM failed to produce valid output"),
            "validation": ValidationResult(valid=False, errors=["LLM output invalid"]),
            "preview_plan": None,
            "summary": "I couldn't generate a valid modification for that request.",
        }

    # ── 2. Validate diff ────────────────────────────────────────────────
    validation = validate_llm_diff(plan, diff, context)

    if not validation.valid:
        return {
            "diff": diff,
            "validation": validation,
            "preview_plan": None,
            "summary": (
                f"The proposed modification failed validation: "
                f"{', '.join(validation.errors[:3])}"
            ),
        }

    # ── 3. Generate preview (merge without persisting) ──────────────────
    preview_plan = merge_base_and_llm(plan, diff)

    # ── 4. Build summary ────────────────────────────────────────────────
    summary = _build_summary(diff, plan, preview_plan)

    return {
        "diff": diff,
        "validation": validation,
        "preview_plan": preview_plan,
        "summary": summary,
    }


def _build_summary(
    diff: LLMDiff,
    original: MachiningPlanResponse,
    preview: MachiningPlanResponse,
) -> str:
    """Build a human-readable summary of proposed changes."""
    parts = [f"**Proposed Changes** ({diff.change_count} modification(s)):"]

    if diff.operation_reorders:
        parts.append(f"- {len(diff.operation_reorders)} operation(s) reordered")
    if diff.tool_changes:
        parts.append(f"- {len(diff.tool_changes)} tool change(s)")
    if diff.parameter_changes:
        parts.append(f"- {len(diff.parameter_changes)} parameter change(s)")
    if diff.setup_modifications:
        parts.append(f"- {len(diff.setup_modifications)} setup modification(s)")
    if diff.operation_additions:
        parts.append(f"- {len(diff.operation_additions)} operation(s) added")

    time_delta = preview.estimated_time - original.estimated_time
    if abs(time_delta) > 0.5:
        sign = "+" if time_delta > 0 else ""
        parts.append(f"- Time impact: {sign}{time_delta:.1f}s")

    parts.append(f"\n**Reason:** {diff.justification}")
    parts.append(f"\nConfidence: {diff.confidence:.0%}")
    parts.append("\n**Reply 'confirm' to apply or 'reject' to discard.**")

    return "\n".join(parts)


async def _call_refinement_llm(
    llm: Any,
    user_message: str,
    plan: MachiningPlanResponse,
    context: PlanningContext,
) -> LLMDiff | None:
    """Single LLM call for refinement diff."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", _REFINEMENT_SYSTEM),
        ("human", _REFINEMENT_USER),
    ])
    parser = JsonOutputParser()
    chain = prompt | llm | parser

    plan_dict = plan.model_dump(exclude={"plan_id"})
    features_json = json.dumps(
        [f.model_dump() for f in context.features], indent=2, default=str
    )

    try:
        result = await chain.ainvoke({
            "material": context.material,
            "machine_type": context.machine_type,
            "plan_json": json.dumps(plan_dict, indent=2, default=str),
            "features_json": features_json,
            "user_message": user_message,
        })
    except Exception:
        logger.exception("Refinement LLM call failed")
        return None

    if not isinstance(result, dict):
        return None

    try:
        return LLMDiff(**result)
    except Exception as exc:
        logger.warning("Failed to parse refinement diff: %s", exc)
        return None
