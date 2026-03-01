"""
Intent Router — classifies user chat messages and routes them.

Intent types:
  - PLAN_MODIFICATION   → refinement engine (structured LLM diff)
  - GENERAL_CONVERSATION → conversational LLM response
  - CONFIRM_CHANGE      → consent manager (apply pending change)
  - REJECT_CHANGE       → consent manager (discard pending change)
  - REQUEST_ALTERNATIVES → alternative generator

Uses keyword heuristics + simple classification.
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate

from ai_service.services.langchain_pipeline import _build_llm

logger = logging.getLogger("ai_service.chat.intent_router")

IntentType = Literal[
    "PLAN_MODIFICATION",
    "GENERAL_CONVERSATION",
    "CONFIRM_CHANGE",
    "REJECT_CHANGE",
    "REQUEST_ALTERNATIVES",
]

# ── Keyword sets ──────────────────────────────────────────────────────────────

_MODIFICATION_KEYWORDS = [
    "change", "modify", "update", "remove", "add", "switch", "replace",
    "use a different", "increase", "decrease", "faster", "slower",
    "make it", "can we", "optimize", "reduce", "combine", "split",
]

_CONFIRM_KEYWORDS = [
    "confirm", "accept", "approve", "yes", "apply", "go ahead",
    "looks good", "do it", "proceed",
]

_REJECT_KEYWORDS = [
    "reject", "cancel", "no", "undo", "discard", "revert", "nevermind",
    "never mind", "forget it",
]

_ALTERNATIVES_KEYWORDS = [
    "alternatives", "other options", "suggestions", "what else",
    "any ideas", "propose", "recommend",
]


_CONVERSATIONAL_SYSTEM_PROMPT = """\
You are MechAI Copilot, a CNC machining assistant.
Answer user questions about:
- Machining processes, tool selection, feeds & speeds
- App functionality, manufacturing best practices
- Current plan details

Context regarding the current plan:
{plan_summary}

Do NOT modify the plan. Return natural language only. No JSON.
"""


class IntentRouter:
    """Routes chat messages to the appropriate handler."""

    @staticmethod
    def classify_intent(user_message: str) -> IntentType:
        """
        Classify user message intent using keyword heuristics.

        Returns:
            IntentType determining which handler processes the message.
        """
        msg_lower = user_message.lower().strip()

        # Confirmation keywords (highest priority)
        for kw in _CONFIRM_KEYWORDS:
            if kw in msg_lower:
                return "CONFIRM_CHANGE"

        # Rejection keywords
        for kw in _REJECT_KEYWORDS:
            if kw in msg_lower:
                return "REJECT_CHANGE"

        # Alternatives request
        for kw in _ALTERNATIVES_KEYWORDS:
            if kw in msg_lower:
                return "REQUEST_ALTERNATIVES"

        # Plan modification
        for kw in _MODIFICATION_KEYWORDS:
            if kw in msg_lower:
                return "PLAN_MODIFICATION"

        # Default: general conversation
        return "GENERAL_CONVERSATION"

    @staticmethod
    async def conversational_response(
        user_message: str,
        plan_summary: str,
    ) -> str:
        """Generate a natural-language response to a general question."""
        llm = _build_llm()
        if not llm:
            return "LLM provider not configured. Please set up an LLM to chat."

        prompt = ChatPromptTemplate.from_messages([
            ("system", _CONVERSATIONAL_SYSTEM_PROMPT),
            ("human", "{user_message}"),
        ])
        chain = prompt | llm

        try:
            result = await chain.ainvoke({
                "plan_summary": plan_summary,
                "user_message": user_message,
            })
            return str(result.content)
        except Exception:
            logger.exception("Conversational LLM call failed")
            return "I'm having trouble processing that right now."
