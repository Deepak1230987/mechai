"""
Rule Engine — deterministic feature-to-operation mapping and sequencing.

Responsibilities:
    1. Map each feature to one or more machining operations
    2. Select the correct tool for each operation via ToolLibrary
    3. Sequence operations according to MILLING_3AXIS / LATHE conventions
    4. Group operations into setups by workpiece orientation

No AI.  No LLM.  Pure if/elif logic + lookup tables.

Future:
    An LLM optimiser can sit on top: receive the baseline plan from this engine,
    propose modifications, and have them re-validated through the same rules.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from ai_service.services.tool_library import ToolLibrary, Tool

logger = logging.getLogger(__name__)

# Re-export for convenience
_lib = ToolLibrary()


# ── Internal intermediate types ───────────────────────────────────────────────

@dataclass
class _PlannedOp:
    """Mutable intermediate before we freeze into OperationSpec."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    feature_id: str = ""
    op_type: str = ""        # DRILLING, POCKET_ROUGHING, etc.
    tool: Tool | None = None
    parameters: dict = field(default_factory=dict)
    sequence_key: int = 0    # for sorting


# ── Sequence priority (lower = earlier) ───────────────────────────────────────
# Milling 3-axis
_MILLING_SEQ: dict[str, int] = {
    "FACE_MILLING":      10,
    "POCKET_ROUGHING":   20,
    "SLOT_MILLING":      30,
    "DRILLING":          40,
    "POCKET_FINISHING":  50,
    "FINISH_CONTOUR":    60,
}

# Lathe
_LATHE_SEQ: dict[str, int] = {
    "ROUGH_TURNING":  10,
    "FINISH_TURNING": 20,
    "GROOVING":       30,
    "DRILLING":       40,   # axial hole on lathe
}


# ── Feature → Operation mapping ──────────────────────────────────────────────

def _plan_hole(
    feature: dict,
    material: str,
    machine_type: str,
) -> list[_PlannedOp]:
    """HOLE → DRILLING (milling or lathe axial drill)."""
    diameter = feature.get("diameter") or feature.get("dimensions", {}).get("diameter", 5.0)
    depth = feature.get("depth") or feature.get("dimensions", {}).get("depth")

    tool = _lib.select_drill(diameter=diameter, depth=depth, material=material)
    if tool is None:
        logger.warning("No drill found for hole d=%.1f, skipping", diameter)
        return []

    seq = _LATHE_SEQ if machine_type == "LATHE" else _MILLING_SEQ
    op = _PlannedOp(
        feature_id=feature["id"],
        op_type="DRILLING",
        tool=tool,
        parameters={"diameter": diameter, "depth": depth},
        sequence_key=seq.get("DRILLING", 40),
    )
    return [op]


def _plan_pocket(
    feature: dict,
    material: str,
    machine_type: str,
) -> list[_PlannedOp]:
    """POCKET → POCKET_ROUGHING + POCKET_FINISHING."""
    dims = feature.get("dimensions", {})
    width = dims.get("width", 10.0)
    depth = feature.get("depth") or dims.get("depth")

    tool = _lib.select_end_mill(pocket_width=width, depth=depth, material=material)
    if tool is None:
        logger.warning("No end mill for pocket w=%.1f, skipping", width)
        return []

    seq = _MILLING_SEQ  # pockets only on milling

    roughing = _PlannedOp(
        feature_id=feature["id"],
        op_type="POCKET_ROUGHING",
        tool=tool,
        parameters={
            "width": width,
            "length": dims.get("length"),
            "depth": depth,
            "stepover_pct": 0.50,   # 50 % stepover for roughing
            "doc_pct": 0.80,        # 80 % of tool diameter axial DOC
        },
        sequence_key=seq.get("POCKET_ROUGHING", 20),
    )
    finishing = _PlannedOp(
        feature_id=feature["id"],
        op_type="POCKET_FINISHING",
        tool=tool,
        parameters={
            "width": width,
            "length": dims.get("length"),
            "depth": depth,
            "stepover_pct": 0.10,   # light finishing pass
            "doc_pct": 1.0,         # full depth in one pass
        },
        sequence_key=seq.get("POCKET_FINISHING", 50),
    )
    return [roughing, finishing]


def _plan_slot(
    feature: dict,
    material: str,
    machine_type: str,
) -> list[_PlannedOp]:
    """SLOT → SLOT_MILLING."""
    dims = feature.get("dimensions", {})
    width = dims.get("width", 6.0)
    depth = feature.get("depth") or dims.get("depth")

    tool = _lib.select_slot_cutter(slot_width=width, depth=depth, material=material)
    if tool is None:
        logger.warning("No slot cutter for slot w=%.1f, skipping", width)
        return []

    op = _PlannedOp(
        feature_id=feature["id"],
        op_type="SLOT_MILLING",
        tool=tool,
        parameters={
            "width": width,
            "length": dims.get("length"),
            "depth": depth,
        },
        sequence_key=_MILLING_SEQ.get("SLOT_MILLING", 30),
    )
    return [op]


def _plan_turn_profile(
    feature: dict,
    material: str,
    machine_type: str,
) -> list[_PlannedOp]:
    """TURN_PROFILE → ROUGH_TURNING + FINISH_TURNING."""
    tool = _lib.select_turning_insert(material=material)
    if tool is None:
        logger.warning("No turning insert found, skipping")
        return []

    dims = feature.get("dimensions", {})
    bbox = dims.get("bounding_box", {})

    roughing = _PlannedOp(
        feature_id=feature["id"],
        op_type="ROUGH_TURNING",
        tool=tool,
        parameters={
            "doc_mm": 2.0,   # 2 mm depth of cut per pass
            "bounding_box": bbox,
        },
        sequence_key=_LATHE_SEQ.get("ROUGH_TURNING", 10),
    )
    finishing = _PlannedOp(
        feature_id=feature["id"],
        op_type="FINISH_TURNING",
        tool=tool,
        parameters={
            "doc_mm": 0.3,   # light finishing cut
            "bounding_box": bbox,
        },
        sequence_key=_LATHE_SEQ.get("FINISH_TURNING", 20),
    )
    return [roughing, finishing]


# ── Dispatcher ────────────────────────────────────────────────────────────────

_PLANNERS: dict[str, callable] = {
    "HOLE":         _plan_hole,
    "POCKET":       _plan_pocket,
    "SLOT":         _plan_slot,
    "TURN_PROFILE": _plan_turn_profile,
}


def plan_operations(
    features: list[dict],
    material: str,
    machine_type: str,
) -> list[_PlannedOp]:
    """
    Map every feature to ordered machining operations.

    Returns a flat list sorted by sequence priority.
    """
    ops: list[_PlannedOp] = []

    for feat in features:
        feat_type = feat.get("type", "")
        planner = _PLANNERS.get(feat_type)
        if planner is None:
            logger.warning("No planner for feature type '%s', skipping", feat_type)
            continue
        planned = planner(feat, material, machine_type)
        ops.extend(planned)

    # Sort by sequence key → deterministic order
    ops.sort(key=lambda o: (o.sequence_key, o.feature_id))
    return ops


# ── Setup grouping ────────────────────────────────────────────────────────────

def group_into_setups(
    ops: list[_PlannedOp],
    machine_type: str,
) -> list[dict]:
    """
    Group operations into physical setups.

    Current strategy (simple):
        - MILLING_3AXIS: single setup, orientation = TOP
        - LATHE: single setup, orientation = CHUCK_Z

    Future: multi-setup logic based on feature axis vectors.
    """
    if not ops:
        return []

    if machine_type == "LATHE":
        orientation = "CHUCK_Z"
    else:
        orientation = "TOP"

    setup = {
        "setup_id": str(uuid.uuid4()),
        "orientation": orientation,
        "operations": [o.id for o in ops],
    }
    return [setup]
