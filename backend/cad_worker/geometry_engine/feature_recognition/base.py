"""
Abstract base class for all feature detectors.

Every detector must implement `detect(shape) -> list[FeatureResult]`.
This ensures the feature factory can call any detector uniformly.

Detectors:
  • HoleDetector       — cylindrical holes (through / blind)
  • PocketDetector     — planar pockets with vertical walls
  • SlotDetector       — parallel-face slots
  • LatheDetector      — rotational symmetry indicators

Future detectors extend this base without modifying existing code.
"""

from __future__ import annotations

import abc
import logging
from typing import Any

from cad_worker.schemas import FeatureResult

logger = logging.getLogger("cad_worker.feature_recognition")


class FeatureDetectorBase(abc.ABC):
    """
    Contract that all feature detectors must fulfil.

    Subclasses implement `detect(shape)` which receives a TopoDS_Shape
    and returns a list of FeatureResult (may be empty).
    """

    @abc.abstractmethod
    def detect(self, shape: Any) -> list[FeatureResult]:
        """
        Detect features of a specific type in the given BRep shape.

        Args:
            shape: An OCC TopoDS_Shape (already validated non-null).

        Returns:
            List of FeatureResult instances. Empty if no features found.

        Raises:
            Must NOT raise — wrap all OCC calls in try/except and log errors.
            Return empty list on failure.
        """
        ...
