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

logger = logging.getLogger(__name__)


# ── Prompts ───────────────────────────────────────────────────────────────────

_CHAT_SYSTEM_PROMPT = """\
You are a CNC process planning expert and machining copilot.

Your job is to modify a machining plan based on the user's instruction.

STRICT RULES:
1. Do NOT invent new features. Only use features already present.
2. Only modify operations, tools, setups, and their parameters.
3. You MAY add/remove/reorder operations for existing features.
4. You MAY change tool selections to equivalent or better tools.
5. You MAY consolidate or split setups.
6. Preserve manufacturability — no physically impossible edits.
7. Always return valid JSON matching the schema below.

Material: {material}
Machine type: {machine_type}

Output MUST be a JSON object with exactly two keys:
{{
  "updated_plan": {{
    "setups": [...],
    "operations": [...],
    "tools": [...],
    "estimated_time": <float>
  }},
  "explanation": "<human-readable reasoning for the changes>"
}}
"""

_CHAT_USER_PROMPT = """\
Current features:
{features_json}

Current machining plan:
{plan_json}

User instruction: {user_message}

Return ONLY the JSON object with "updated_plan" and "explanation" keys.
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

    # ── 2. Build LLM ─────────────────────────────────────────────────────
    llm = _build_llm()
    if llm is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM provider not configured — chat refinement requires an LLM",
        )

    # ── 3. Call LLM (with retry) ─────────────────────────────────────────
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="LLM could not produce a valid plan modification",
        )

    updated_plan_dict = llm_result["updated_plan"]
    explanation = llm_result["explanation"]

    # ── 4. Overlay immutable fields ───────────────────────────────────────
    updated_plan_dict["model_id"] = plan.model_id
    updated_plan_dict["material"] = material
    updated_plan_dict["machine_type"] = machine_type

    # ── 5. Validate updated plan ──────────────────────────────────────────
    pv = PlanValidator(unique_features, material, machine_type)
    try:
        validated = pv.validate(updated_plan_dict)
    except PlanValidationError as exc:
        logger.warning(
            "Chat-refined plan failed validation: %s — returning error",
            exc.errors,
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"LLM-generated plan failed validation: {exc.errors}",
        )

    # ── 6. Compute next version ───────────────────────────────────────────
    max_version_result = await session.execute(
        select(func.coalesce(func.max(MachiningPlan.version), 0)).where(
            MachiningPlan.model_id == plan.model_id
        )
    )
    next_version: int = max_version_result.scalar_one() + 1

    validated["version"] = next_version
    validated["approved"] = False

    # ── 7. Persist new version ────────────────────────────────────────────
    new_plan = MachiningPlan(
        id=str(uuid.uuid4()),
        model_id=plan.model_id,
        material=material,
        machine_type=machine_type,
        plan_data=validated,
        estimated_time=validated.get("estimated_time", 0),
        version=next_version,
        approved=False,
    )
    session.add(new_plan)

    logger.info(
        "Chat refinement: model=%s v%d→v%d | instruction=%r",
        plan.model_id,
        plan.version,
        next_version,
        user_message[:80],
    )

    return {
        "explanation": explanation,
        "new_plan": new_plan,
        "new_version": next_version,
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

    if "updated_plan" not in result or "explanation" not in result:
        logger.warning(
            "Chat LLM missing keys. Got: %s",
            list(result.keys()),
        )
        return None

    up = result["updated_plan"]
    required = {"setups", "operations", "tools", "estimated_time"}
    if not required.issubset(up.keys()):
        logger.warning(
            "Chat LLM updated_plan missing keys: %s",
            required - up.keys(),
        )
        return None

    return result
