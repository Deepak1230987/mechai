"""
LangChain Pipeline — multi-provider LLM-based plan optimisation layer.

Supports:
    • OpenAI       (gpt-4o, gpt-4o-mini, o3-mini, …)
    • Anthropic    (claude-sonnet-4-20250514, claude-3-haiku, …)
    • Google       (gemini-2.0-flash, gemini-1.5-pro, …)
    • Ollama       (llama3, mistral, codestral, …)
    • none         (LLM disabled — returns baseline plan unchanged)

The provider and model are configured via environment variables:
    LLM_PROVIDER=openai          # openai | anthropic | google | ollama | none
    LLM_MODEL=gpt-4o             # model name for the chosen provider
    LLM_API_KEY=sk-…             # required for cloud providers
    LLM_TEMPERATURE=0.1
    LLM_MAX_TOKENS=4096
    LLM_BASE_URL=                # optional custom endpoint
    OLLAMA_HOST=http://localhost:11434

Safety:
    • LLM must NOT invent features
    • Structured output parser enforces schema compliance
    • Single retry on failure
    • Fallback to base_plan on any error

The rule engine remains the ground truth.  The LLM is an optimiser,
never the primary planner.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from shared.config import get_settings

logger = logging.getLogger(__name__)


# ── Provider factory ──────────────────────────────────────────────────────────

def _build_llm() -> BaseChatModel | None:
    """
    Construct a LangChain chat model from Settings.

    Returns None when LLM_PROVIDER is "none" or empty.
    """
    s = get_settings()
    provider = (s.LLM_PROVIDER or "none").strip().lower()

    if provider == "none" or not provider:
        logger.info("LLM_PROVIDER='none' — LLM optimisation disabled")
        return None

    model = s.LLM_MODEL
    if not model:
        logger.warning("LLM_MODEL is empty — disabling LLM optimisation")
        return None

    common: dict[str, Any] = {
        "temperature": s.LLM_TEMPERATURE,
        "max_tokens": s.LLM_MAX_TOKENS,
    }

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": model,
            "api_key": s.LLM_API_KEY or None,
            **common,
        }
        if s.LLM_BASE_URL:
            kwargs["base_url"] = s.LLM_BASE_URL
        return ChatOpenAI(**kwargs)

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        kwargs = {
            "model": model,
            "api_key": s.LLM_API_KEY or None,
            **common,
        }
        if s.LLM_BASE_URL:
            kwargs["base_url"] = s.LLM_BASE_URL
        return ChatAnthropic(**kwargs)

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs = {
            "model": model,
            "google_api_key": s.LLM_API_KEY or None,
            **common,
        }
        return ChatGoogleGenerativeAI(**kwargs)

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        kwargs = {
            "model": model,
            "api_key": s.LLM_API_KEY or None,
            "base_url": s.LLM_BASE_URL or "https://openrouter.ai/api/v1",
            **common,
            "default_headers": {
                "HTTP-Referer": "https://mechai.dev",
                "X-Title": "MechAI CAM Planner",
            },
        }
        return ChatOpenAI(**kwargs)

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        kwargs = {
            "model": model,
            "base_url": s.OLLAMA_HOST,
            "temperature": s.LLM_TEMPERATURE,
            # Ollama uses num_predict instead of max_tokens
            "num_predict": s.LLM_MAX_TOKENS,
        }
        return ChatOllama(**kwargs)

    logger.error("Unknown LLM_PROVIDER=%r — disabling LLM optimisation", provider)
    return None


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a CNC machining process optimiser.

You receive a baseline machining plan (JSON) produced by a deterministic rule
engine. Your job is to OPTIMISE the plan — not replace it.

RULES:
1. Do NOT invent new features.  Only use features present in the input.
2. Do NOT remove features or operations.  Every feature must be machined.
3. You MAY reorder operations for reduced tool changes.
4. You MAY consolidate setups if orientations are compatible.
5. You MAY suggest alternative tools from the same category (e.g. a larger
   end mill that covers two pockets in one pass).
6. Preserve all required fields in the output JSON.
7. Determine if any suggested changes were made, and provide a short, professional explanation of your optimization reasoning. If you made no changes, explain why the baseline was already optimal.
8. The output must be valid JSON matching the input schema EXACTLY, plus an "explanation" field.

Material: {material}
Machine type: {machine_type}
"""

_USER_PROMPT = """\
Validated features:
{features_json}

Baseline plan:
{plan_json}

Return the optimised plan as a single JSON object with keys:
explanation, setups, operations, tools, estimated_time.
"""


# ── Public API ────────────────────────────────────────────────────────────────

async def optimize_plan(
    base_plan: dict,
    validated_features: list[dict],
    material: str,
    machine_type: str,
) -> dict:
    """
    Attempt LLM-based optimisation of a rule-engine plan.

    Args:
        base_plan:           MachiningPlanResponse.model_dump()
        validated_features:  Validated feature dicts
        material:            Workpiece material string
        machine_type:        MILLING_3AXIS | LATHE

    Returns:
        Optimised plan dict (same schema as base_plan) or base_plan on failure.
    """
    llm = _build_llm()
    if llm is None:
        logger.debug("No LLM configured — returning base plan unchanged")
        return base_plan

    try:
        result = await _call_llm(llm, base_plan, validated_features, material, machine_type)
        if result is not None:
            logger.info("LLM optimisation applied successfully (provider=%s)", type(llm).__name__)
            return result
    except Exception:
        logger.exception("LLM optimisation failed on first attempt")

    # ── Retry once ────────────────────────────────────────────────────────
    try:
        result = await _call_llm(llm, base_plan, validated_features, material, machine_type)
        if result is not None:
            logger.info("LLM optimisation applied on retry")
            return result
    except Exception:
        logger.exception("LLM optimisation failed on retry — falling back to base plan")

    return base_plan


# ── Private ───────────────────────────────────────────────────────────────────

async def _call_llm(
    llm: BaseChatModel,
    base_plan: dict,
    validated_features: list[dict],
    material: str,
    machine_type: str,
) -> dict | None:
    """Single LLM call with structured output parsing."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        ("human", _USER_PROMPT),
    ])

    parser = JsonOutputParser()

    chain = prompt | llm | parser

    features_json = json.dumps(validated_features, indent=2, default=str)
    plan_json = json.dumps(base_plan, indent=2, default=str)

    result = await chain.ainvoke({
        "material": material,
        "machine_type": machine_type,
        "features_json": features_json,
        "plan_json": plan_json,
    })

    # Basic structural validation — must have required keys
    if not isinstance(result, dict):
        logger.warning("LLM returned non-dict: %s", type(result))
        return None

    required_keys = {"explanation", "setups", "operations", "tools", "estimated_time"}
    if not required_keys.issubset(result.keys()):
        missing = required_keys - result.keys()
        logger.warning("LLM output missing keys: %s", missing)
        return None

    # Preserve model_id, material, machine_type from base plan
    result["model_id"] = base_plan["model_id"]
    result["material"] = base_plan["material"]
    result["machine_type"] = base_plan["machine_type"]

    return result
