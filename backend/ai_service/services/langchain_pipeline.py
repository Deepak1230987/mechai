"""
LangChain Pipeline — multi-provider LLM factory.

Provides _build_llm(), the canonical LLM factory used by ALL modules:
  • planning/llm_coplanner.py
  • reasoning/narrative_generator.py
  • reasoning/alternative_generator.py
  • chat/intent_router.py
  • chat/refinement_engine.py

Supports:
    • OpenAI       (gpt-4o, gpt-4o-mini, o3-mini, …)
    • Anthropic    (claude-sonnet-4-20250514, claude-3-haiku, …)
    • Google       (gemini-2.0-flash, gemini-1.5-pro, …)
    • Ollama       (llama3, mistral, codestral, …)
    • none         (LLM disabled — returns None)

The provider and model are configured via environment variables:
    LLM_PROVIDER=openai          # openai | anthropic | google | ollama | none
    LLM_MODEL=gpt-4o             # model name for the chosen provider
    LLM_API_KEY=sk-…             # required for cloud providers
    LLM_TEMPERATURE=0.1
    LLM_MAX_TOKENS=4096
    LLM_BASE_URL=                # optional custom endpoint
    OLLAMA_HOST=http://localhost:11434
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

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

    logger.error("Unknown LLM_PROVIDER=%r — disabling LLM", provider)
    return None
