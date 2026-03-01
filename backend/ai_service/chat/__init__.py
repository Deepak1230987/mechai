"""Chat layer — intent routing, refinement engine, consent management."""

from .intent_router import IntentRouter
from .refinement_engine import generate_refinement_diff
from .consent_manager import ConsentManager

__all__ = [
    "IntentRouter",
    "generate_refinement_diff",
    "ConsentManager",
]
