"""
Feature factory — runs all registered detectors on a BRep shape.

This is the single entry point for feature recognition.
The worker calls `detect_all_features(shape)` and gets back
a flat list of FeatureResult from all detectors.

Adding a new detector requires only:
  1. Create the detector class extending FeatureDetectorBase
  2. Register it in _DETECTORS list below
No existing detector code is modified.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from cad_worker.schemas import FeatureResult
from cad_worker.geometry_engine.feature_recognition.base import FeatureDetectorBase
from cad_worker.geometry_engine.feature_recognition.hole_detector import HoleDetector
from cad_worker.geometry_engine.feature_recognition.pocket_detector import PocketDetector
from cad_worker.geometry_engine.feature_recognition.slot_detector import SlotDetector
from cad_worker.geometry_engine.feature_recognition.lathe_detector import LatheDetector

logger = logging.getLogger("cad_worker.feature_factory")

# ── Registered detectors (order matters for de-dup priority) ─────────────────
_DETECTORS: list[type[FeatureDetectorBase]] = [
    HoleDetector,
    PocketDetector,
    SlotDetector,
    LatheDetector,
]


def detect_all_features(shape: Any) -> list[FeatureResult]:
    """
    Run all registered feature detectors on a BRep shape.

    Args:
        shape: An OCC TopoDS_Shape (must be valid BRep, not mesh).

    Returns:
        Flat list of FeatureResult from all detectors.
        Empty list if no features detected or on failure.
    """
    all_features: list[FeatureResult] = []
    total_start = time.monotonic()

    for detector_cls in _DETECTORS:
        detector_name = detector_cls.__name__
        start = time.monotonic()

        try:
            detector = detector_cls()
            results = detector.detect(shape)
            elapsed = time.monotonic() - start

            logger.info(
                f"  {detector_name}: {len(results)} features in {elapsed:.3f}s"
            )
            all_features.extend(results)

        except Exception as e:
            elapsed = time.monotonic() - start
            logger.error(
                f"  {detector_name}: FAILED after {elapsed:.3f}s — {e}",
                exc_info=True,
            )
            # Continue with other detectors — don't let one failure
            # prevent detection of other feature types

    total_elapsed = time.monotonic() - total_start
    logger.info(
        f"Feature recognition complete: {len(all_features)} total features "
        f"in {total_elapsed:.3f}s"
    )

    return all_features
