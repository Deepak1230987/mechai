"""
Intelligence modules for manufacturing geometry analysis.

This package contains deterministic (NO AI/LLM) analysis engines:
  • stock_recommender  — raw stock type and size recommendation
  • datum_detector     — datum face candidate selection
  • manufacturability_analyzer — manufacturability warning detection
  • complexity_scorer  — normalized complexity scoring
"""

from .stock_recommender import recommend_stock
from .datum_detector import detect_datums
from .manufacturability_analyzer import analyze
from .complexity_scorer import compute_complexity

__all__ = [
    "recommend_stock",
    "detect_datums",
    "analyze",
    "compute_complexity",
]
