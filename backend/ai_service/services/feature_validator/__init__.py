"""
Feature Validator — abstract interface for the ML boundary.

Every validator implementation (deterministic, Vertex AI, ensemble) MUST
subclass FeatureValidator and implement validate().

planning_service depends ONLY on this interface.
The concrete implementation is injected at call time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class FeatureValidator(ABC):
    """
    Abstract base for feature validation.

    Sits between raw detected features and the rule engine.
    Responsibilities:
        • Re-score feature confidence
        • Remove clearly invalid features
        • Add manufacturability hints
        • Return a validated feature list

    Must NOT access:
        • Rule engine
        • LangChain / LLM
        • Database directly
    """

    @abstractmethod
    def validate(
        self,
        features: list[dict],
        geometry_metadata: dict,
    ) -> list[dict]:
        """
        Validate and filter a list of detected features.

        Args:
            features:          Raw feature dicts from DB (id, type, dimensions, ...).
            geometry_metadata: Geometry metrics (bounding_box, volume, surface_area, ...).

        Returns:
            Validated feature list — same schema as input, with confidence
            re-scored and invalid features removed.
        """
        ...
