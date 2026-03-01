"""
LLM Co-Planner — produces structured diffs against the deterministic base plan.

The LLM receives:
  - Base plan (full MachiningPlanResponse)
  - Full intelligence report
  - Material + machine type
  - Optimization goal

The LLM outputs LLMDiff ONLY — never a full plan.

Safety:
  - LLM cannot create new features
  - LLM cannot remove safety operations
  - LLM must reference feature IDs exactly
  - Output must be valid JSON matching LLMDiff schema
  - Single retry on failure
  - Returns empty diff on any error (deterministic plan preserved)
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
from ai_service.services.langchain_pipeline import _build_llm

logger = logging.getLogger("ai_service.planning.llm_coplanner")


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a CNC machining co-planner. You receive a deterministic base plan
and must propose IMPROVEMENTS as a structured diff.

You MUST output a JSON object matching this exact schema:
{{
  "operation_reorders": [
    {{"operation_id": "<existing-op-id>", "new_position": <int>, "reason": "<why>"}}
  ],
  "tool_changes": [
    {{
      "operation_id": "<existing-op-id>",
      "current_tool_id": "<current>",
      "proposed_tool_id": "<new>",
      "proposed_tool_type": "<type>",
      "proposed_tool_diameter": <float>,
      "reason": "<why>"
    }}
  ],
  "parameter_changes": [
    {{
      "operation_id": "<existing-op-id>",
      "parameter_name": "<param>",
      "old_value": <value>,
      "new_value": <value>,
      "reason": "<why>"
    }}
  ],
  "setup_modifications": [
    {{
      "action": "MERGE|SPLIT|REORDER",
      "setup_ids": ["<id1>", "<id2>"],
      "proposed_orientation": "<orientation>",
      "operations_to_move": ["<op-id>"],
      "reason": "<why>"
    }}
  ],
  "operation_additions": [
    {{
      "feature_id": "<MUST be existing feature ID>",
      "op_type": "<operation type>",
      "insert_after": "<op-id or null>",
      "tool_type": "<type>",
      "tool_diameter": <float>,
      "parameters": {{}},
      "reason": "<why>"
    }}
  ],
  "justification": "<overall reasoning>",
  "estimated_time_change": <float seconds, negative=faster>,
  "confidence": <float 0-1>
}}

STRICT RULES:
1. Do NOT create new features. Only reference existing feature IDs.
2. Do NOT remove safety operations (spot drilling, finishing passes for tight tolerances).
3. Reference feature IDs and operation IDs EXACTLY as given.
4. Output ONLY the JSON diff object. No markdown, no commentary.
5. If the base plan is already optimal, return empty lists with justification explaining why.
6. Optimize for: {optimization_goal}

Material: {material}
Machine type: {machine_type}
Complexity score: {complexity}
"""

_USER_PROMPT = """\
Base plan:
{plan_json}

Intelligence report features:
{features_json}

Manufacturability warnings:
{warnings_json}

Propose improvements as a structured diff.
"""


# ── Public API ────────────────────────────────────────────────────────────────

async def refine_plan_with_llm(
    base_plan: MachiningPlanResponse,
    context: PlanningContext,
) -> LLMDiff:
    """
    Call LLM to produce a structured diff improving the base plan.

    Returns:
        LLMDiff (may be empty if LLM is disabled or fails).
    """
    llm = _build_llm()
    if llm is None:
        logger.debug("No LLM configured — returning empty diff")
        return LLMDiff(justification="LLM disabled — base plan unchanged")

    # Attempt with retry
    for attempt in range(2):
        try:
            diff = await _call_llm(llm, base_plan, context)
            if diff is not None:
                logger.info(
                    "LLM co-planner produced diff: %d changes, confidence=%.2f",
                    diff.change_count, diff.confidence,
                )
                return diff
        except Exception:
            logger.exception(
                "LLM co-planner attempt %d failed", attempt + 1
            )

    logger.warning("LLM co-planner failed — returning empty diff")
    return LLMDiff(justification="LLM optimization failed — base plan preserved")


async def _call_llm(
    llm: Any,
    base_plan: MachiningPlanResponse,
    context: PlanningContext,
) -> LLMDiff | None:
    """Single LLM call. Returns LLMDiff or None."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human", _USER_PROMPT),
    ])

    parser = JsonOutputParser()
    chain = prompt | llm | parser

    plan_dict = base_plan.model_dump(exclude={"plan_id"})
    features_json = json.dumps(
        [f.model_dump() for f in context.features],
        indent=2, default=str,
    )
    warnings_json = json.dumps(
        [f.model_dump() for f in context.manufacturability_flags],
        indent=2, default=str,
    )

    result = await chain.ainvoke({
        "optimization_goal": context.optimization_goal,
        "material": context.material,
        "machine_type": context.machine_type,
        "complexity": context.complexity_score,
        "plan_json": json.dumps(plan_dict, indent=2, default=str),
        "features_json": features_json,
        "warnings_json": warnings_json,
    })

    if not isinstance(result, dict):
        logger.warning("LLM returned non-dict: %s", type(result))
        return None

    try:
        diff = LLMDiff(**result)
    except Exception as exc:
        logger.warning("LLM output failed LLMDiff validation: %s", exc)
        return None

    return diff
