"""Reasoning layer — narrative generation and alternative suggestions."""

from .narrative_generator import generate_narrative
from .alternative_generator import generate_alternatives

__all__ = [
    "generate_narrative",
    "generate_alternatives",
]
