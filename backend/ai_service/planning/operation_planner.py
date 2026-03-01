"""
Operation Planner — maps features to machining operations.

Rules:
  HOLE:
    1. Spot drill (centering)
    2. Drill
    3. Ream (if tolerance ≤ 0.02 mm)

  POCKET:
    1. Rough mill
    2. Finish mill

  SLOT:
    1. Rough slot
    2. Finish pass

  TURN_PROFILE:
    1. Rough turning
    2. Finish turning

Sequencing:
  - Face milling first
  - Rough before finish
  - Deeper features earlier (better chip evacuation)
  - Each operation references feature_id

No LLM. Deterministic mapping only.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from ai_service.schemas.planning_context import PlanningContext, FeatureContext

logger = logging.getLogger("ai_service.planning.operation_planner")


# ── Sequence priority (lower = earlier) ──────────────────────────────────────

_MILLING_SEQ: dict[str, int] = {
    "FACE_MILLING":       5,
    "SPOT_DRILL":        10,
    "DRILLING":          15,
    "REAMING":           18,
    "POCKET_ROUGHING":   20,
    "SLOT_ROUGHING":     30,
    "POCKET_FINISHING":  50,
    "SLOT_FINISHING":    55,
    "FINISH_CONTOUR":    60,
    "CHAMFER":           65,
}

_LATHE_SEQ: dict[str, int] = {
    "ROUGH_TURNING":  10,
    "FINISH_TURNING": 20,
    "GROOVING":       30,
    "DRILLING":       40,
}


@dataclass
class PlannedOperation:
    """Intermediate operation before freezing into OperationSpec."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    feature_id: str = ""
    op_type: str = ""
    tool_hint: str = ""          # tool type hint for tool_planner
    parameters: dict = field(default_factory=dict)
    sequence_key: int = 0
    depth_priority: float = 0.0  # deeper = lower number = earlier


def plan_operations(context: PlanningContext) -> list[PlannedOperation]:
    """
    Map every feature to ordered machining operations.

    Returns flat list sorted by (sequence_key, depth_priority, feature_id).
    """
    ops: list[PlannedOperation] = []
    seq_table = _LATHE_SEQ if context.machine_type == "LATHE" else _MILLING_SEQ

    for feat in context.features:
        feat_ops = _dispatch_feature(feat, context, seq_table)
        ops.extend(feat_ops)

    # Sort: sequence priority → deeper first → stable on feature_id
    ops.sort(key=lambda o: (o.sequence_key, -o.depth_priority, o.feature_id))

    logger.info(
        "Operation planning: %d features → %d operations",
        len(context.features), len(ops),
    )
    return ops


# ── Feature dispatchers ──────────────────────────────────────────────────────

def _dispatch_feature(
    feat: FeatureContext,
    context: PlanningContext,
    seq: dict[str, int],
) -> list[PlannedOperation]:
    """Route feature to its operation planner."""
    ftype = feat.type.upper()
    if ftype == "HOLE":
        return _plan_hole(feat, context, seq)
    if ftype == "POCKET":
        return _plan_pocket(feat, context, seq)
    if ftype == "SLOT":
        return _plan_slot(feat, context, seq)
    if ftype == "TURN_PROFILE":
        return _plan_turn_profile(feat, context, seq)
    if ftype == "FACE":
        return _plan_face(feat, context, seq)
    if ftype == "CONTOUR":
        return _plan_contour(feat, context, seq)
    logger.warning("No operation planner for feature type '%s'", ftype)
    return []


def _plan_hole(
    feat: FeatureContext,
    context: PlanningContext,
    seq: dict[str, int],
) -> list[PlannedOperation]:
    """HOLE → Spot + Drill + optional Ream."""
    diameter = feat.diameter or feat.dimensions.get("diameter", 5.0)
    depth = feat.depth or feat.dimensions.get("depth", 10.0)
    ops: list[PlannedOperation] = []

    # 1. Spot drill for centering
    ops.append(PlannedOperation(
        feature_id=feat.id,
        op_type="SPOT_DRILL",
        tool_hint="DRILL",
        parameters={"diameter": diameter, "depth": min(diameter * 0.3, 2.0)},
        sequence_key=seq.get("SPOT_DRILL", 10),
        depth_priority=depth,
    ))

    # 2. Drill
    ops.append(PlannedOperation(
        feature_id=feat.id,
        op_type="DRILLING",
        tool_hint="DRILL",
        parameters={"diameter": diameter, "depth": depth},
        sequence_key=seq.get("DRILLING", 15),
        depth_priority=depth,
    ))

    # 3. Ream if tight tolerance
    if feat.tolerance is not None and feat.tolerance <= 0.02:
        ops.append(PlannedOperation(
            feature_id=feat.id,
            op_type="REAMING",
            tool_hint="DRILL",
            parameters={"diameter": diameter, "depth": depth, "tolerance": feat.tolerance},
            sequence_key=seq.get("REAMING", 18),
            depth_priority=depth,
        ))

    return ops


def _plan_pocket(
    feat: FeatureContext,
    context: PlanningContext,
    seq: dict[str, int],
) -> list[PlannedOperation]:
    """POCKET → Rough mill + Finish mill."""
    dims = feat.dimensions
    width = dims.get("width", 10.0)
    length = dims.get("length", width)
    depth = feat.depth or dims.get("depth", 5.0)

    roughing = PlannedOperation(
        feature_id=feat.id,
        op_type="POCKET_ROUGHING",
        tool_hint="FLAT_END_MILL",
        parameters={
            "width": width, "length": length, "depth": depth,
            "stepover_pct": 0.50, "doc_pct": 0.80,
        },
        sequence_key=seq.get("POCKET_ROUGHING", 20),
        depth_priority=depth,
    )
    finishing = PlannedOperation(
        feature_id=feat.id,
        op_type="POCKET_FINISHING",
        tool_hint="FLAT_END_MILL",
        parameters={
            "width": width, "length": length, "depth": depth,
            "stepover_pct": 0.10, "doc_pct": 1.0,
        },
        sequence_key=seq.get("POCKET_FINISHING", 50),
        depth_priority=depth,
    )
    return [roughing, finishing]


def _plan_slot(
    feat: FeatureContext,
    context: PlanningContext,
    seq: dict[str, int],
) -> list[PlannedOperation]:
    """SLOT → Rough slot + Finish pass."""
    dims = feat.dimensions
    width = dims.get("width", 6.0)
    length = dims.get("length", 20.0)
    depth = feat.depth or dims.get("depth", 5.0)

    roughing = PlannedOperation(
        feature_id=feat.id,
        op_type="SLOT_ROUGHING",
        tool_hint="SLOT_CUTTER",
        parameters={"width": width, "length": length, "depth": depth},
        sequence_key=seq.get("SLOT_ROUGHING", 30),
        depth_priority=depth,
    )
    finishing = PlannedOperation(
        feature_id=feat.id,
        op_type="SLOT_FINISHING",
        tool_hint="SLOT_CUTTER",
        parameters={"width": width, "length": length, "depth": depth},
        sequence_key=seq.get("SLOT_FINISHING", 55),
        depth_priority=depth,
    )
    return [roughing, finishing]


def _plan_turn_profile(
    feat: FeatureContext,
    context: PlanningContext,
    seq: dict[str, int],
) -> list[PlannedOperation]:
    """TURN_PROFILE → Rough turning + Finish turning."""
    dims = feat.dimensions
    bbox = dims.get("bounding_box", {})

    roughing = PlannedOperation(
        feature_id=feat.id,
        op_type="ROUGH_TURNING",
        tool_hint="TURNING_INSERT",
        parameters={"doc_mm": 2.0, "bounding_box": bbox},
        sequence_key=seq.get("ROUGH_TURNING", 10),
        depth_priority=feat.depth or 0,
    )
    finishing = PlannedOperation(
        feature_id=feat.id,
        op_type="FINISH_TURNING",
        tool_hint="TURNING_INSERT",
        parameters={"doc_mm": 0.3, "bounding_box": bbox},
        sequence_key=seq.get("FINISH_TURNING", 20),
        depth_priority=feat.depth or 0,
    )
    return [roughing, finishing]


def _plan_face(
    feat: FeatureContext,
    context: PlanningContext,
    seq: dict[str, int],
) -> list[PlannedOperation]:
    """FACE → Face milling pass (roughing + finishing)."""
    dims = feat.dimensions
    length = dims.get("length", 100.0)
    width = dims.get("width", 50.0)
    depth = feat.depth or dims.get("depth", 1.0)

    roughing = PlannedOperation(
        feature_id=feat.id,
        op_type="FACE_MILLING",
        tool_hint="FACE_MILL",
        parameters={
            "length": length, "width": width,
            "depth": depth, "doc_pct": 0.60,
            "stepover_pct": 0.75,
        },
        sequence_key=seq.get("FACE_MILLING", 5),
        depth_priority=depth,
    )
    return [roughing]


def _plan_contour(
    feat: FeatureContext,
    context: PlanningContext,
    seq: dict[str, int],
) -> list[PlannedOperation]:
    """CONTOUR → Rough contour + Finish contour pass."""
    dims = feat.dimensions
    perimeter = dims.get("length", 100.0)
    depth = feat.depth or dims.get("depth", 5.0)

    roughing = PlannedOperation(
        feature_id=feat.id,
        op_type="POCKET_ROUGHING",
        tool_hint="FLAT_END_MILL",
        parameters={
            "perimeter": perimeter, "depth": depth,
            "stepover_pct": 0.50, "doc_pct": 0.80,
        },
        sequence_key=seq.get("POCKET_ROUGHING", 20),
        depth_priority=depth,
    )
    finishing = PlannedOperation(
        feature_id=feat.id,
        op_type="FINISH_CONTOUR",
        tool_hint="FLAT_END_MILL",
        parameters={
            "perimeter": perimeter, "depth": depth,
            "stepover_pct": 0.10, "doc_pct": 1.0,
        },
        sequence_key=seq.get("FINISH_CONTOUR", 60),
        depth_priority=depth,
    )
    return [roughing, finishing]
