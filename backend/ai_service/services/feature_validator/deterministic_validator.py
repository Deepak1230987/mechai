"""
Deterministic Feature Validator — rule-based feature validation.

Responsibilities:
    • Re-score feature confidence based on geometric plausibility
    • Remove features that are clearly invalid (impossible dimensions)
    • Add manufacturability hints (e.g. "thin_wall", "deep_hole")
    • Return a validated, filtered feature list

Does NOT access:
    • Rule engine
    • LangChain / LLM
    • Database

This is the default validator used in production until Vertex AI is ready.
"""

from __future__ import annotations

import logging
import copy

from ai_service.services.feature_validator import FeatureValidator

logger = logging.getLogger(__name__)

# ── Physical limits for sanity checks ─────────────────────────────────────────

_MIN_DIMENSION_MM = 0.1      # Anything smaller is likely noise
_MAX_DIMENSION_MM = 5000.0   # 5 m — beyond typical CNC envelope
_MIN_CONFIDENCE = 0.3        # Below this → discard
_DEEP_HOLE_RATIO = 5.0       # depth / diameter > 5 → deep hole flag
_THIN_WALL_MM = 1.0          # Wall thickness below 1 mm → warning


class DeterministicFeatureValidator(FeatureValidator):
    """
    Pure rule-based feature validator.

    Validation rules:
        1. Reject features with confidence < 0.3
        2. Reject features with impossible dimensions (≤ 0, > 5000 mm)
        3. Re-score confidence based on geometric fit to bounding box
        4. Flag deep holes (L/D > 5) and thin walls (< 1 mm)
        5. Ensure feature dimensions fit within model bounding box
    """

    def validate(
        self,
        features: list[dict],
        geometry_metadata: dict,
    ) -> list[dict]:
        """Validate features against geometry metadata."""
        bbox = geometry_metadata.get("bounding_box", {})
        volume = geometry_metadata.get("volume", 0.0)

        # Compute max model dimension — handle both bbox formats:
        #   Format A: {"x_min": ..., "x_max": ..., "y_min": ..., "y_max": ..., "z_min": ..., "z_max": ...}
        #   Format B: {"length": ..., "width": ..., "height": ...}
        if "length" in bbox or "width" in bbox or "height" in bbox:
            model_dims = [
                abs(bbox.get("length", 0.0)),
                abs(bbox.get("width", 0.0)),
                abs(bbox.get("height", 0.0)),
            ]
        else:
            model_dims = [
                abs(bbox.get("x_max", 100) - bbox.get("x_min", 0)),
                abs(bbox.get("y_max", 100) - bbox.get("y_min", 0)),
                abs(bbox.get("z_max", 100) - bbox.get("z_min", 0)),
            ]
        max_model_dim = max(model_dims) if model_dims else 100.0

        validated: list[dict] = []
        for raw in features:
            feat = copy.deepcopy(raw)

            # ── Confidence gate ─────────────────────────────────────────
            conf = feat.get("confidence", 0.0)
            if conf < _MIN_CONFIDENCE:
                logger.debug(
                    "Rejected feature %s: confidence %.2f < %.2f",
                    feat.get("id"), conf, _MIN_CONFIDENCE,
                )
                continue

            # ── Dimension sanity ────────────────────────────────────────
            if not self._check_dimensions(feat, max_model_dim):
                logger.debug(
                    "Rejected feature %s: invalid dimensions", feat.get("id"),
                )
                continue

            # ── Re-score confidence ─────────────────────────────────────
            feat["confidence"] = self._rescore(feat, max_model_dim, volume)

            # ── Manufacturability hints ─────────────────────────────────
            hints = self._compute_hints(feat)
            if hints:
                feat["hints"] = hints

            validated.append(feat)

        logger.info(
            "Validation: %d raw → %d validated features",
            len(features), len(validated),
        )
        return validated

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _check_dimensions(feat: dict, max_model_dim: float) -> bool:
        """Return False if any dimension is physically impossible."""
        dims = feat.get("dimensions", {})

        for key in ("width", "length", "depth", "diameter"):
            val = dims.get(key) or feat.get(key)
            if val is not None:
                if val <= _MIN_DIMENSION_MM or val > _MAX_DIMENSION_MM:
                    return False
                # Feature dimension shouldn't exceed model bounding box
                if val > max_model_dim * 1.5:
                    return False
        return True

    @staticmethod
    def _rescore(feat: dict, max_model_dim: float, volume: float) -> float:
        """
        Adjust confidence based on geometric plausibility.

        Boosts:
            • Feature dimensions are reasonable fraction of model size → +0.05
            • Feature has well-defined axis → +0.03
        Penalties:
            • Feature volume > 50% of model volume → -0.1
            • Missing critical dimensions → -0.05
        """
        conf = feat.get("confidence", 0.5)
        dims = feat.get("dimensions", {})
        feat_type = feat.get("type", "")

        # Boost: reasonable fraction of model (1–50%)
        max_feat_dim = max(
            (dims.get(k) or 0.0 for k in ("width", "length", "depth", "diameter")),
            default=0.0,
        )
        if 0 < max_feat_dim <= max_model_dim * 0.5:
            conf += 0.05

        # Boost: well-defined axis
        axis = feat.get("axis")
        if axis and isinstance(axis, dict):
            conf += 0.03

        # Penalty: oversized feature
        feat_vol = _estimate_feature_volume(feat_type, dims, feat)
        if volume > 0 and feat_vol > volume * 0.5:
            conf -= 0.10

        # Penalty: missing critical dims
        if feat_type == "HOLE" and not (dims.get("diameter") or feat.get("diameter")):
            conf -= 0.05
        if feat_type == "POCKET" and not dims.get("width"):
            conf -= 0.05

        return round(max(0.0, min(1.0, conf)), 3)

    @staticmethod
    def _compute_hints(feat: dict) -> list[str]:
        """Flag manufacturability concerns."""
        hints: list[str] = []
        dims = feat.get("dimensions", {})
        feat_type = feat.get("type", "")

        if feat_type == "HOLE":
            diameter = dims.get("diameter") or feat.get("diameter") or 0
            depth = dims.get("depth") or feat.get("depth") or 0
            if diameter > 0 and depth / diameter > _DEEP_HOLE_RATIO:
                hints.append("deep_hole")

        if feat_type == "POCKET":
            depth = dims.get("depth") or feat.get("depth") or 0
            width = dims.get("width") or 0
            if width > 0 and depth > 0:
                wall = width * 0.1  # rough wall estimate
                if wall < _THIN_WALL_MM:
                    hints.append("thin_wall")

        return hints


def _estimate_feature_volume(feat_type: str, dims: dict, feat: dict) -> float:
    """Rough volume estimate for sanity check."""
    import math

    if feat_type == "HOLE":
        d = dims.get("diameter") or feat.get("diameter") or 5.0
        h = dims.get("depth") or feat.get("depth") or 10.0
        return math.pi * (d / 2) ** 2 * h
    elif feat_type in ("POCKET", "SLOT"):
        w = dims.get("width") or 10.0
        l = dims.get("length") or w
        d = dims.get("depth") or 5.0
        return w * l * d
    return 0.0
