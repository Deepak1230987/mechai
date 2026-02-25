"""
Time Estimator — deterministic machining time calculation.

Formula per operation:
    time (s) = material_removal_volume (mm³) / MRR (mm³/s)

MRR is a constant lookup indexed by (tool_type, material_class).
Volume is approximated from feature dimensions + tool parameters.

No AI.  No simulation.  Physically reasonable ballpark estimates.
"""

from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)


# ── Material Removal Rate table (mm³ / second) ──────────────────────────────
# Conservative shop-floor values.
# Keys: (tool_type, material_class)

_MRR: dict[tuple[str, str], float] = {
    # Drills
    ("DRILL", "ALUMINUM"):  120.0,
    ("DRILL", "STEEL"):      50.0,
    ("DRILL", "TITANIUM"):   25.0,
    ("DRILL", "PLASTIC"):   180.0,

    # Flat end mills
    ("FLAT_END_MILL", "ALUMINUM"):  200.0,
    ("FLAT_END_MILL", "STEEL"):      80.0,
    ("FLAT_END_MILL", "TITANIUM"):   35.0,
    ("FLAT_END_MILL", "PLASTIC"):   300.0,

    # Ball end mills (lower MRR due to point contact)
    ("BALL_END_MILL", "ALUMINUM"):  100.0,
    ("BALL_END_MILL", "STEEL"):      40.0,
    ("BALL_END_MILL", "TITANIUM"):   18.0,
    ("BALL_END_MILL", "PLASTIC"):   150.0,

    # Slot cutters
    ("SLOT_CUTTER", "ALUMINUM"):  150.0,
    ("SLOT_CUTTER", "STEEL"):      60.0,
    ("SLOT_CUTTER", "TITANIUM"):   28.0,
    ("SLOT_CUTTER", "PLASTIC"):   220.0,

    # Turning inserts
    ("TURNING_INSERT", "ALUMINUM"):  500.0,
    ("TURNING_INSERT", "STEEL"):     200.0,
    ("TURNING_INSERT", "TITANIUM"):   80.0,
    ("TURNING_INSERT", "PLASTIC"):   700.0,
}

# Fallback MRR if no lookup exists
_DEFAULT_MRR = 60.0


# ── Material class normalisation (same map as tool_library) ──────────────────

_MATERIAL_MAP: dict[str, str] = {
    "ALUMINUM": "ALUMINUM", "ALUMINUM_6061": "ALUMINUM", "ALUMINUM_7075": "ALUMINUM",
    "STEEL": "STEEL", "STEEL_1045": "STEEL", "STEEL_4140": "STEEL",
    "STAINLESS_304": "STEEL", "STAINLESS_316": "STEEL",
    "TITANIUM": "TITANIUM", "TITANIUM_GR5": "TITANIUM",
    "PLASTIC": "PLASTIC", "DELRIN": "PLASTIC", "NYLON": "PLASTIC", "ABS": "PLASTIC",
}


def _normalise(material: str) -> str:
    return _MATERIAL_MAP.get(material.upper().strip(), "STEEL")


# ── Volume approximation per operation type ──────────────────────────────────

def _volume_drilling(params: dict, tool_diameter: float) -> float:
    """Cylinder volume: π r² h"""
    d = params.get("diameter", tool_diameter)
    depth = params.get("depth") or 10.0
    r = d / 2.0
    return math.pi * r * r * depth


def _volume_pocket(params: dict, tool_diameter: float) -> float:
    """Rectangular prism approximation: L × W × D"""
    w = params.get("width") or 10.0
    l = params.get("length") or w  # square pocket fallback
    d = params.get("depth") or 5.0
    return l * w * d


def _volume_slot(params: dict, tool_diameter: float) -> float:
    """Slot = W × L × D  (like a narrow pocket)."""
    w = params.get("width") or 6.0
    l = params.get("length") or 20.0
    d = params.get("depth") or 5.0
    return l * w * d


def _volume_turning(params: dict, tool_diameter: float) -> float:
    """
    Rough turning: annular volume between stock and finished diameter.

    Approximation: use bounding box to infer stock cylinder then remove 20 %.
    """
    bbox = params.get("bounding_box", {})
    dx = bbox.get("dx", 50.0)
    dy = bbox.get("dy", 50.0)
    dz = bbox.get("dz", 100.0)
    stock_radius = max(dx, dy) / 2.0
    length = dz
    stock_vol = math.pi * stock_radius * stock_radius * length
    return stock_vol * 0.20  # assume 20 % material removal


_VOLUME_FN: dict[str, callable] = {
    "DRILLING":         _volume_drilling,
    "POCKET_ROUGHING":  _volume_pocket,
    "POCKET_FINISHING": lambda p, d: _volume_pocket(p, d) * 0.05,  # 5 % skin pass
    "SLOT_MILLING":     _volume_slot,
    "ROUGH_TURNING":    _volume_turning,
    "FINISH_TURNING":   lambda p, d: _volume_turning(p, d) * 0.10,  # 10 % of rough
    "FACE_MILLING":     _volume_pocket,
    "FINISH_CONTOUR":   lambda p, d: _volume_pocket(p, d) * 0.05,
    "GROOVING":         lambda p, d: 200.0,  # small fixed volume
}


# ── Public API ────────────────────────────────────────────────────────────────

def estimate_operation_time(
    op_type: str,
    tool_type: str,
    tool_diameter: float,
    material: str,
    parameters: dict,
) -> float:
    """
    Estimate machining time for a single operation.

    Returns: time in seconds (≥ 1.0, clamped).
    """
    mat = _normalise(material)
    mrr = _MRR.get((tool_type, mat), _DEFAULT_MRR)

    vol_fn = _VOLUME_FN.get(op_type)
    if vol_fn is None:
        logger.warning("No volume function for op_type '%s', using 500 mm³", op_type)
        volume = 500.0
    else:
        volume = vol_fn(parameters, tool_diameter)

    if volume <= 0:
        return 1.0

    time_s = volume / mrr
    # Clamp minimum 1 second (tool change / approach overhead)
    return max(time_s, 1.0)


def estimate_total_time(operation_times: list[float]) -> float:
    """Sum all operation times + 30 s per setup overhead."""
    if not operation_times:
        return 0.0
    # Add 30 s setup overhead per plan (minimal single-setup)
    return sum(operation_times) + 30.0
