"""
Tool Library — deterministic tool selection for the rule-based planner.

Every tool is a plain dict stored in a lookup table.  Tool selection is driven
by three inputs:

    1. Feature type (HOLE, POCKET, SLOT, TURN_PROFILE)
    2. Material class (ALUMINUM, STEEL, TITANIUM, PLASTIC)
    3. Machine type  (MILLING_3AXIS, LATHE)

Tool selection rules:
    • Drill ↔ HOLE   (diameter matched to feature)
    • Flat end mill ↔ POCKET (diameter = 60% of pocket width)
    • Slot cutter / end mill ↔ SLOT  (diameter ≤ slot width)
    • Turning insert ↔ TURN_PROFILE

No database.  No AI calls.  Pure in-memory catalogue.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── Tool dataclass (internal catalogue entry) ─────────────────────────────────

@dataclass(frozen=True)
class Tool:
    id: str
    type: str               # DRILL | FLAT_END_MILL | BALL_END_MILL | SLOT_CUTTER | TURNING_INSERT
    diameter: float          # mm
    max_depth: float         # mm
    materials: tuple[str, ...] = ()   # compatible material classes
    rpm_min: int = 0
    rpm_max: int = 0


# ── Standard catalogue ───────────────────────────────────────────────────────
# Expand as real tooling is sourced.  Each entry is a physically valid tool.

_CATALOGUE: list[Tool] = [
    # ── Drills ────────────────────────────────────────────────────────────────
    Tool("drill-1mm",   "DRILL", 1.0,  30,  ("ALUMINUM", "STEEL", "PLASTIC"), 3000, 8000),
    Tool("drill-2mm",   "DRILL", 2.0,  50,  ("ALUMINUM", "STEEL", "PLASTIC"), 2500, 7000),
    Tool("drill-3mm",   "DRILL", 3.0,  60,  ("ALUMINUM", "STEEL", "PLASTIC"), 2000, 6000),
    Tool("drill-4mm",   "DRILL", 4.0,  80,  ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 1800, 5500),
    Tool("drill-5mm",   "DRILL", 5.0,  100, ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 1500, 5000),
    Tool("drill-6mm",   "DRILL", 6.0,  100, ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 1200, 4500),
    Tool("drill-8mm",   "DRILL", 8.0,  120, ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 1000, 4000),
    Tool("drill-10mm",  "DRILL", 10.0, 150, ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 800,  3500),
    Tool("drill-12mm",  "DRILL", 12.0, 150, ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 700,  3000),
    Tool("drill-16mm",  "DRILL", 16.0, 180, ("ALUMINUM", "STEEL", "TITANIUM"),            600,  2500),
    Tool("drill-20mm",  "DRILL", 20.0, 200, ("ALUMINUM", "STEEL", "TITANIUM"),            500,  2000),
    Tool("drill-25mm",  "DRILL", 25.0, 200, ("ALUMINUM", "STEEL"),                        400,  1500),

    # ── Flat end mills ────────────────────────────────────────────────────────
    Tool("fem-1mm",  "FLAT_END_MILL", 1.0,  8,   ("ALUMINUM", "PLASTIC"),                      8000, 20000),
    Tool("fem-2mm",  "FLAT_END_MILL", 2.0,  12,  ("ALUMINUM", "STEEL", "PLASTIC"),              6000, 16000),
    Tool("fem-3mm",  "FLAT_END_MILL", 3.0,  20,  ("ALUMINUM", "STEEL", "PLASTIC"),           4000, 12000),
    Tool("fem-4mm",  "FLAT_END_MILL", 4.0,  25,  ("ALUMINUM", "STEEL", "PLASTIC"),           3500, 10000),
    Tool("fem-6mm",  "FLAT_END_MILL", 6.0,  35,  ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 3000, 9000),
    Tool("fem-8mm",  "FLAT_END_MILL", 8.0,  45,  ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 2500, 8000),
    Tool("fem-10mm", "FLAT_END_MILL", 10.0, 50,  ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 2000, 7000),
    Tool("fem-12mm", "FLAT_END_MILL", 12.0, 60,  ("ALUMINUM", "STEEL", "TITANIUM"),           1800, 6000),
    Tool("fem-16mm", "FLAT_END_MILL", 16.0, 80,  ("ALUMINUM", "STEEL", "TITANIUM"),           1500, 5000),
    Tool("fem-20mm", "FLAT_END_MILL", 20.0, 100, ("ALUMINUM", "STEEL"),                      1200, 4000),
    Tool("fem-25mm", "FLAT_END_MILL", 25.0, 100, ("ALUMINUM", "STEEL"),                      1000, 3500),

    # ── Ball end mills ────────────────────────────────────────────────────────
    Tool("bem-3mm",  "BALL_END_MILL", 3.0,  20, ("ALUMINUM", "STEEL", "PLASTIC"),           4000, 12000),
    Tool("bem-6mm",  "BALL_END_MILL", 6.0,  35, ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 3000, 9000),
    Tool("bem-10mm", "BALL_END_MILL", 10.0, 50, ("ALUMINUM", "STEEL", "TITANIUM"),           2000, 7000),

    # ── Slot cutters ──────────────────────────────────────────────────────────
    Tool("sc-4mm",  "SLOT_CUTTER", 4.0,  15, ("ALUMINUM", "STEEL", "PLASTIC"), 3000, 8000),
    Tool("sc-6mm",  "SLOT_CUTTER", 6.0,  20, ("ALUMINUM", "STEEL", "PLASTIC"), 2500, 7000),
    Tool("sc-8mm",  "SLOT_CUTTER", 8.0,  30, ("ALUMINUM", "STEEL", "TITANIUM"), 2000, 6000),
    Tool("sc-10mm", "SLOT_CUTTER", 10.0, 40, ("ALUMINUM", "STEEL", "TITANIUM"), 1800, 5000),
    Tool("sc-12mm", "SLOT_CUTTER", 12.0, 50, ("ALUMINUM", "STEEL"),            1500, 4000),

    # ── Turning inserts ───────────────────────────────────────────────────────
    Tool("ti-0.4mm", "TURNING_INSERT", 0.4, 5,   ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 500, 3000),
    Tool("ti-0.8mm", "TURNING_INSERT", 0.8, 8,   ("ALUMINUM", "STEEL", "TITANIUM", "PLASTIC"), 400, 2500),
    Tool("ti-1.2mm", "TURNING_INSERT", 1.2, 10,  ("ALUMINUM", "STEEL", "TITANIUM"),            300, 2000),
]


# ── Indices for fast lookup ──────────────────────────────────────────────────
_BY_TYPE: dict[str, list[Tool]] = {}
for _tool in _CATALOGUE:
    _BY_TYPE.setdefault(_tool.type, []).append(_tool)


# ── Material normalisation map ────────────────────────────────────────────────
# User strings like "ALUMINUM_6061" → catalogue class "ALUMINUM"
_MATERIAL_MAP: dict[str, str] = {
    "ALUMINUM":      "ALUMINUM",
    "ALUMINUM_6061": "ALUMINUM",
    "ALUMINUM_7075": "ALUMINUM",
    "STEEL":         "STEEL",
    "STEEL_1045":    "STEEL",
    "STEEL_4140":    "STEEL",
    "STAINLESS_304": "STEEL",
    "STAINLESS_316": "STEEL",
    "TITANIUM":      "TITANIUM",
    "TITANIUM_GR5":  "TITANIUM",
    "PLASTIC":       "PLASTIC",
    "DELRIN":        "PLASTIC",
    "NYLON":         "PLASTIC",
    "ABS":           "PLASTIC",
}


def _normalise_material(material: str) -> str:
    """Map user-facing material string to internal class."""
    key = material.upper().strip()
    cls = _MATERIAL_MAP.get(key)
    if cls is None:
        logger.warning("Unknown material '%s', defaulting to STEEL", material)
        return "STEEL"
    return cls


# ── Public API ────────────────────────────────────────────────────────────────

class ToolLibrary:
    """
    Deterministic tool selector.

    Usage:
        lib = ToolLibrary()
        tool = lib.select_drill(diameter=5.0, material="ALUMINUM_6061")
        tool = lib.select_end_mill(pocket_width=12.0, material="STEEL_1045")
    """

    # ── Drill for HOLE features ──────────────────────────────────────────────

    @staticmethod
    def select_drill(
        diameter: float,
        depth: float | None,
        material: str,
    ) -> Tool | None:
        """
        Pick the smallest drill that matches the hole diameter.

        Selection rules:
            1. Filter drills by material compatibility
            2. Find the drill whose diameter is closest to the feature diameter
               (prefer exact match, then next-larger)
            3. Verify max_depth is sufficient
        """
        mat = _normalise_material(material)
        candidates = [
            t for t in _BY_TYPE.get("DRILL", [])
            if mat in t.materials
        ]
        if not candidates:
            return None

        # Prefer exact or next-larger diameter
        candidates.sort(key=lambda t: (abs(t.diameter - diameter), t.diameter))
        best = candidates[0]

        # Depth check
        if depth is not None and depth > best.max_depth:
            # Try to find a drill that can reach
            deep_enough = [t for t in candidates if t.max_depth >= depth]
            deep_enough.sort(key=lambda t: abs(t.diameter - diameter))
            if deep_enough:
                best = deep_enough[0]
            else:
                logger.warning(
                    "No drill can reach depth %.1f mm for diameter %.1f",
                    depth, diameter,
                )
                # Still return the closest diameter match
        return best

    # ── Flat end mill for POCKET features ────────────────────────────────────

    @staticmethod
    def select_end_mill(
        pocket_width: float,
        depth: float | None,
        material: str,
    ) -> Tool | None:
        """
        Pick a flat end mill for pocket milling.

        Rule: tool diameter ≈ 60 % of pocket width (standard practice).
        """
        mat = _normalise_material(material)
        target_dia = pocket_width * 0.6

        candidates = [
            t for t in _BY_TYPE.get("FLAT_END_MILL", [])
            if mat in t.materials
        ]
        if not candidates:
            return None

        # Closest to target without exceeding pocket width
        valid = [t for t in candidates if t.diameter <= pocket_width]
        if not valid:
            return None

        valid.sort(key=lambda t: abs(t.diameter - target_dia))
        best = valid[0]

        # Depth check
        if depth is not None and depth > best.max_depth:
            deep_enough = [
                t for t in valid if t.max_depth >= depth
            ]
            if deep_enough:
                deep_enough.sort(key=lambda t: abs(t.diameter - target_dia))
                best = deep_enough[0]

        return best

    # ── Slot cutter for SLOT features ────────────────────────────────────────

    @staticmethod
    def select_slot_cutter(
        slot_width: float,
        depth: float | None,
        material: str,
    ) -> Tool | None:
        """
        Pick a slot cutter or end mill that fits the slot width.

        Tool diameter must be ≤ slot width.
        """
        mat = _normalise_material(material)

        # Try dedicated slot cutters first, fall back to flat end mills
        for tool_type in ("SLOT_CUTTER", "FLAT_END_MILL"):
            candidates = [
                t for t in _BY_TYPE.get(tool_type, [])
                if mat in t.materials and t.diameter <= slot_width
            ]
            if not candidates:
                continue

            # Largest that fits (maximise MRR)
            candidates.sort(key=lambda t: t.diameter, reverse=True)
            best = candidates[0]

            if depth is not None and depth > best.max_depth:
                deep_enough = [t for t in candidates if t.max_depth >= depth]
                if deep_enough:
                    deep_enough.sort(key=lambda t: t.diameter, reverse=True)
                    best = deep_enough[0]

            return best

        return None

    # ── Turning insert for TURN_PROFILE features ─────────────────────────────

    @staticmethod
    def select_turning_insert(material: str) -> Tool | None:
        """Pick a turning insert for lathe operations."""
        mat = _normalise_material(material)
        candidates = [
            t for t in _BY_TYPE.get("TURNING_INSERT", [])
            if mat in t.materials
        ]
        if not candidates:
            return None
        # Default to mid-size insert
        candidates.sort(key=lambda t: t.diameter)
        return candidates[len(candidates) // 2]
