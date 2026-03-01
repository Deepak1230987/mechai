"""
Setup Planner — groups features into physical setups by accessibility.

Logic:
  1. Use primary datum as reference face
  2. Group features by accessibility_direction
  3. Same direction → same setup
  4. Opposite direction → new setup (workpiece flip)
  5. Undercuts / multi-axis features → flagged setup

No LLM. Pure deterministic grouping.
"""

from __future__ import annotations

import logging
import uuid

from ai_service.schemas.planning_context import PlanningContext, FeatureContext

logger = logging.getLogger("ai_service.planning.setup_planner")

# Default orientations by accessibility direction
_DIRECTION_TO_ORIENTATION: dict[str, str] = {
    "TOP": "TOP",
    "BOTTOM": "BOTTOM",
    "FRONT": "FRONT",
    "BACK": "BACK",
    "LEFT": "LEFT",
    "RIGHT": "RIGHT",
}

# Axis-based fallback: determine direction from axis vector
def _infer_direction(feature: FeatureContext) -> str:
    """Infer accessibility direction from feature axis or default to TOP."""
    if feature.accessibility_direction:
        return feature.accessibility_direction.upper()

    axis = feature.axis
    if axis and isinstance(axis, dict):
        z = abs(axis.get("z", 0))
        y = abs(axis.get("y", 0))
        x = abs(axis.get("x", 0))
        if z >= y and z >= x:
            return "BOTTOM" if axis.get("z", 0) < 0 else "TOP"
        if y >= x:
            return "BACK" if axis.get("y", 0) < 0 else "FRONT"
        return "LEFT" if axis.get("x", 0) < 0 else "RIGHT"

    return "TOP"


def plan_setups(context: PlanningContext) -> list[dict]:
    """
    Group features into setups by accessibility direction.

    Returns:
        List of setup dicts:
          {
            "setup_id": str,
            "orientation": str,
            "datum_face_id": str | None,
            "feature_ids": list[str],
            "requires_flip": bool,
            "is_undercut": bool,
          }
    """
    if context.machine_type == "LATHE":
        return _plan_lathe_setups(context)

    return _plan_milling_setups(context)


def _plan_milling_setups(context: PlanningContext) -> list[dict]:
    """Group milling features by accessibility direction."""
    groups: dict[str, list[str]] = {}
    flip_features: list[str] = []
    multi_axis_features: list[str] = []

    for feat in context.features:
        if feat.requires_multi_axis:
            multi_axis_features.append(feat.id)
            continue

        direction = _infer_direction(feat)
        groups.setdefault(direction, []).append(feat.id)

        if feat.requires_flip:
            flip_features.append(feat.id)

    setups: list[dict] = []

    # Primary setup = TOP (or datum direction)
    primary_dir = "TOP"
    if primary_dir in groups:
        setups.append({
            "setup_id": str(uuid.uuid4()),
            "orientation": _DIRECTION_TO_ORIENTATION.get(primary_dir, primary_dir),
            "datum_face_id": context.datum_primary,
            "feature_ids": groups.pop(primary_dir),
            "requires_flip": False,
            "is_undercut": False,
        })

    # Remaining directions → additional setups
    for direction, feat_ids in sorted(groups.items()):
        setups.append({
            "setup_id": str(uuid.uuid4()),
            "orientation": _DIRECTION_TO_ORIENTATION.get(direction, direction),
            "datum_face_id": context.datum_primary,
            "feature_ids": feat_ids,
            "requires_flip": direction == "BOTTOM" or any(
                fid in flip_features for fid in feat_ids
            ),
            "is_undercut": False,
        })

    # Multi-axis features → flagged setup
    if multi_axis_features:
        setups.append({
            "setup_id": str(uuid.uuid4()),
            "orientation": "MULTI_AXIS",
            "datum_face_id": context.datum_primary,
            "feature_ids": multi_axis_features,
            "requires_flip": False,
            "is_undercut": True,
        })

    # Ensure at least one setup
    if not setups:
        setups.append({
            "setup_id": str(uuid.uuid4()),
            "orientation": "TOP",
            "datum_face_id": context.datum_primary,
            "feature_ids": [f.id for f in context.features],
            "requires_flip": False,
            "is_undercut": False,
        })

    logger.info(
        "Setup planning: %d features → %d setups (machine=%s)",
        len(context.features), len(setups), context.machine_type,
    )
    return setups


def _plan_lathe_setups(context: PlanningContext) -> list[dict]:
    """Lathe: single chuck setup with optional tail-stock support."""
    return [{
        "setup_id": str(uuid.uuid4()),
        "orientation": "CHUCK_Z",
        "datum_face_id": context.datum_primary,
        "feature_ids": [f.id for f in context.features],
        "requires_flip": False,
        "is_undercut": False,
    }]
