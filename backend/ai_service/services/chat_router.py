"""
Chat Router Service - Directs user messages to either conversational AI
or structured plan modification.
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate

from ai_service.services.langchain_pipeline import _build_llm

logger = logging.getLogger(__name__)

IntentType = Literal["PLAN_MODIFICATION", "GENERAL_CONVERSATION"]

# Keywords that strongly suggest a plan modification
MODIFICATION_KEYWORDS = [
    "change", "modify", "update", "remove", "add", "switch", "replace",
    "use a different", "increase", "decrease", "faster", "slower",
    "make it", "can we",
]

_CONVERSATIONAL_SYSTEM_PROMPT = """\
You are MechAI Copilot, a CNC machining assistant.
Answer user questions about:
- Machining processes
- Tool selection
- Feeds and speeds
- App functionality
- Manufacturing best practices

Context regarding the current plan:
{plan_summary}

Do NOT modify the plan unless explicitly instructed.
Return natural language only. No JSON. Provide helpful, concise answers.
"""


class ChatRouter:
    """Routes chat messages and handles general conversation."""

    @staticmethod
    def classify_intent(user_message: str) -> IntentType:
        """
        Determine if the user wants to chat or modify the plan.
        Uses simple keyword heuristics.
        """
        msg_lower = user_message.lower().strip()
        
        # Very short messages are usually conversational
        if len(msg_lower) < 15 and not any(kw in msg_lower for kw in MODIFICATION_KEYWORDS):
            return "GENERAL_CONVERSATION"

        # Check for modification keywords
        for keyword in MODIFICATION_KEYWORDS:
            if keyword in msg_lower:
                return "PLAN_MODIFICATION"

        # Default to conversation if ambiguous
        return "GENERAL_CONVERSATION"

    @staticmethod
    async def conversational_llm_response(
        user_message: str,
        plan_context_summary: str,
    ) -> str:
        """
        Generate a natural language response to a general question.
        """
        llm = _build_llm()
        if not llm:
            return "I am currently offline, please configure my LLM provider settings to chat."

        prompt = ChatPromptTemplate.from_messages([
            ("system", _CONVERSATIONAL_SYSTEM_PROMPT),
            ("human", "{user_message}"),
        ])

        chain = prompt | llm

        try:
            result = await chain.ainvoke({
                "plan_summary": plan_context_summary,
                "user_message": user_message,
            })
            return str(result.content)
        except Exception:
            logger.exception("Conversational LLM call failed")
            return "I'm sorry, I'm having trouble processing that request right now."
