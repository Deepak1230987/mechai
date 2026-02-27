"""
Chat Refinement Service — conversational plan modification via LLM.

Flow:
    1. Fetch current plan + features from DB
    2. Build LangChain prompt with plan context + user instruction
    3. Parse structured JSON output: {updated_plan, explanation}
    4. Validate the updated plan via PlanValidator
    5. Create new immutable plan version (approved=False)
    6. Return explanation + new version

Uses the same LLM provider factory as langchain_pipeline.py.
Never invents features — only modifies operations/tools/setups.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import HTTPException, status
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ai_service.models import MachiningPlan
from ai_service.services.langchain_pipeline import _build_llm
from ai_service.services.plan_validator import PlanValidator, PlanValidationError
from ai_service.services.chat_router import ChatRouter

logger = logging.getLogger(__name__)


# ── Prompts ───────────────────────────────────────────────────────────────────

_CHAT_SYSTEM_PROMPT = """\
You are a CNC process planning optimizer.

Your job is to modify a machining plan based on the user's instruction.

STRICT RULES:
1. Determine if the user's instruction is physically possible and adheres to best CNC machining practices.
2. If the request is impossible, unsafe, or violates physics/geometry, set "is_possible" to false and explain why in "explanation". Also, do not output "updated_plan" in this case.
3. If the request is possible, set "is_possible" to true, and provide the modified plan in "updated_plan".
4. Do NOT invent new features. Only use features already present.
5. Only modify operations, tools, setups, and their parameters.
6. You MAY add/remove/reorder operations for existing features.
7. You MAY change tool selections to equivalent or better tools.
8. You MAY consolidate or split setups.
9. Preserve manufacturability — no physically impossible edits.
10. Always return valid JSON matching the schema below.

Material: {material}
Machine type: {machine_type}

Output MUST be a JSON object with this shape:
{{
  "is_possible": <boolean>,
  "explanation": "<human-readable reasoning for the changes or why it's impossible>",
  "updated_plan": {{
    "setups": [...],
    "operations": [...],
    "tools": [...],
    "estimated_time": <float>
  }} // Omit "updated_plan" if is_possible is false.
}}
"""

_CHAT_USER_PROMPT = """\
Current features:
{features_json}

Current machining plan:
{plan_json}

User instruction: {user_message}

Return ONLY the required JSON object.
"""


# ── Public API ────────────────────────────────────────────────────────────────

async def chat_refine_plan(
    plan_id: str,
    user_message: str,
    session: AsyncSession,
) -> dict[str, Any]:
    """
    Conversational plan refinement.

    Args:
        plan_id:       ID of the current plan to refine.
        user_message:  Natural-language instruction from the user.
        session:       Async DB session.

    Returns:
        {
            "explanation": str,
            "new_plan": MachiningPlan,   # SQLAlchemy row
            "new_version": int,
        }

    Raises:
        HTTPException 404  — plan not found
        HTTPException 422  — LLM output fails validation
        HTTPException 503  — LLM unavailable
    """

    # ── 1. Fetch current plan ─────────────────────────────────────────────
    plan = await session.get(MachiningPlan, plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found",
        )

    plan_data: dict = plan.plan_data
    material = plan.material
    machine_type = plan.machine_type

    # Extract feature stubs from existing operations
    feature_stubs = [
        {"id": op["feature_id"], "type": op.get("type", "UNKNOWN")}
        for op in plan_data.get("operations", [])
    ]
    # De-duplicate
    seen = set()
    unique_features: list[dict] = []
    for f in feature_stubs:
        if f["id"] not in seen:
            seen.add(f["id"])
            unique_features.append(f)

    # ── 2. Route Intent ──────────────────────────────────────────────────
    intent = ChatRouter.classify_intent(user_message)
    
    # Simple plan summary for general conversation context
    plan_summary = (
        f"Material: {material}, Machine: {machine_type}. "
        f"{len(plan_data.get('operations', []))} operations, "
        f"{len(plan_data.get('setups', []))} setups. "
        f"Estimated time: {plan_data.get('estimated_time', 0)} mins."
    )

    if intent == "GENERAL_CONVERSATION":
        logger.info("Chat intent: GENERAL_CONVERSATION")
        text_response = await ChatRouter.conversational_llm_response(
            user_message, plan_summary
        )
        return {
            "type": "conversation",
            "message": text_response,
        }

    logger.info("Chat intent: PLAN_MODIFICATION. Proceeding with structured edit.")

    # ── 3. Build LLM ─────────────────────────────────────────────────────
    llm = _build_llm()
    if llm is None:
        # Fallback to general conversation error message since we don't want to throw 503
        return {
            "type": "conversation",
            "message": "LLM provider is not configured. Structured plan modification is unavailable.",
        }

    # ── 4. Call LLM (with retry and fallback) ────────────────────────────
    llm_result = await _call_chat_llm(
        llm, plan_data, unique_features, material, machine_type, user_message,
    )
    if llm_result is None:
        # Retry once
        logger.warning("Chat LLM first attempt returned None — retrying")
        llm_result = await _call_chat_llm(
            llm, plan_data, unique_features, material, machine_type, user_message,
        )
    if llm_result is None:
        logger.warning("Failed to generate valid JSON modification. Falling back to conversation.")
        fallback_msg = await ChatRouter.conversational_llm_response(user_message, plan_summary)
        return {"type": "conversation", "message": fallback_msg}

    explanation = llm_result.get("explanation", "Plan proposed by AI.")
    is_possible = llm_result.get("is_possible", True)

    if not is_possible:
        return {"type": "conversation", "message": explanation}

    updated_plan_dict = llm_result.get("updated_plan")
    if not updated_plan_dict:
        return {"type": "conversation", "message": "I couldn't generate a valid plan for that request. " + explanation}

    # ── 5. Overlay immutable fields ───────────────────────────────────────
    updated_plan_dict["model_id"] = plan.model_id
    updated_plan_dict["material"] = material
    updated_plan_dict["machine_type"] = machine_type

    # ── 6. Validate updated plan ──────────────────────────────────────────
    pv = PlanValidator(unique_features, material, machine_type)
    try:
        validated = pv.validate(updated_plan_dict)
    except PlanValidationError as exc:
        logger.warning(
            "Chat-refined plan failed validation: %s — falling back to conversation",
            exc.errors,
        )
        fallback_msg = (
            f"I tried to modify the plan according to your instruction, but it resulted in an invalid configuration: "
            f"{exc.errors[0].get('msg', 'Validation error')}."
        )
        return {"type": "conversation", "message": fallback_msg}

    # Do not persist the plan yet ! That requires user consent via the UI.
    # We will instantiate a MachiningPlan model object in memory to return
    # it in the correct format for MachiningPlanResponse
    
    # ── 7. Prepare proposed plan to return ──────────────────────────────────
    validated["version"] = plan.version  # The proposed plan implicitly edits the current version
    validated["approved"] = False
    
    proposed_plan = MachiningPlan(
        id=plan.id, # Keep original DB id for reference
        model_id=plan.model_id,
        material=material,
        machine_type=machine_type,
        plan_data=validated,
        estimated_time=validated.get("estimated_time", 0),
        version=plan.version,
        approved=False,
    )

    logger.info("Chat refinement proposed new plan for model=%s", plan.model_id)

    return {
        "type": "plan_proposal",
        "explanation": explanation,
        "proposed_plan": proposed_plan,
        "new_version": plan.version,
    }


# ── Private helpers ───────────────────────────────────────────────────────────

async def _call_chat_llm(
    llm: Any,
    plan_data: dict,
    features: list[dict],
    material: str,
    machine_type: str,
    user_message: str,
) -> dict | None:
    """
    Single LLM call for chat refinement.

    Returns:
        {"updated_plan": {...}, "explanation": "..."} or None on failure.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", _CHAT_SYSTEM_PROMPT),
        ("human", _CHAT_USER_PROMPT),
    ])

    parser = JsonOutputParser()
    chain = prompt | llm | parser

    try:
        result = await chain.ainvoke({
            "material": material,
            "machine_type": machine_type,
            "features_json": json.dumps(features, indent=2, default=str),
            "plan_json": json.dumps(plan_data, indent=2, default=str),
            "user_message": user_message,
        })
    except Exception:
        logger.exception("Chat LLM call failed")
        return None

    if not isinstance(result, dict):
        logger.warning("Chat LLM returned non-dict: %s", type(result))
        return None

    if "is_possible" not in result or "explanation" not in result:
        logger.warning(
            "Chat LLM missing keys. Got: %s",
            list(result.keys()),
        )
        return None

    if result.get("is_possible") and "updated_plan" not in result:
        logger.warning("Chat LLM updated_plan missing when is_possible is true.")
        return None

    if result.get("is_possible"):
        up = result["updated_plan"]
        required = {"setups", "operations", "tools", "estimated_time"}
        if not required.issubset(up.keys()):
            logger.warning(
                "Chat LLM updated_plan missing keys: %s",
                required - up.keys(),
            )
            return None

    return result
