"""
FeatureResult — canonical output contract for all feature detectors.

Every detector (hole, pocket, slot, lathe) MUST return a list of FeatureResult.
This is a pure data class with no ORM dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FeatureResult:
    """
    A single detected machining feature.

    Attributes:
        type:           Feature type (HOLE, POCKET, SLOT, TURN_PROFILE).
        dimensions:     Feature-specific dimensions dict.
        depth:          Feature depth (nullable).
        diameter:       Feature diameter — holes only (nullable).
        axis:           Axis direction vector {x, y, z} (nullable).
        tolerance:      Tolerance value (nullable, future use).
        surface_finish: Surface finish spec (nullable, future use).
        confidence:     Detection confidence 0.0–1.0.
    """

    type: str
    dimensions: dict = field(default_factory=dict)
    depth: float | None = None
    diameter: float | None = None
    axis: dict | None = None
    tolerance: float | None = None
    surface_finish: str | None = None
    confidence: float = 0.0

    _VALID_TYPES = {"HOLE", "POCKET", "SLOT", "TURN_PROFILE"}

    def __post_init__(self) -> None:
        if self.type not in self._VALID_TYPES:
            raise ValueError(
                f"Feature type must be one of {self._VALID_TYPES}, got '{self.type}'"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"Confidence must be 0.0–1.0, got {self.confidence}"
            )
