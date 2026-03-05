"""Conversation layer — context-aware manufacturing intelligence (Phase C)."""

from .context_builder import build_conversation_context, ConversationContext
from .conversational_engine import conversational_engine_answer
from .general_query_handler import handle_general_query
from .impact_simulator import simulate_impact
from .explanation_engine import explain_feature, explain_operation
from .narrative_builder import build_initial_narrative

__all__ = [
    "build_conversation_context",
    "ConversationContext",
    "conversational_engine_answer",
    "handle_general_query",
    "simulate_impact",
    "explain_feature",
    "explain_operation",
    "build_initial_narrative",
]
