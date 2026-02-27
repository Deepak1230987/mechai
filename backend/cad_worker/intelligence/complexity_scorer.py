"""
Complexity Scorer — normalized machining complexity assessment.

Produces a ComplexityScore with:
  • value: float in [0.0, 1.0]
  • level: LOW / MEDIUM / HIGH

WEIGHTED FORMULA
================
Score = 0.3·F + 0.2·W + 0.2·S + 0.2·T + 0.1·A

Where:
  F = Feature count (normalized)
  W = Warning severity weight (normalized)
  S = Estimated setup count (normalized)
  T = Tool diversity estimate (normalized)
  A = Accessibility penalty (normalized)

NORMALIZATION STRATEGY
======================
Each component is normalized to [0.0, 1.0] using a saturation function:

  normalized(x, x_max) = min(x / x_max, 1.0)

This maps the raw value to a 0-1 range where x_max represents "maximum
expected complexity." Values above x_max saturate to 1.0.

Saturation maxima (calibrated against industrial part surveys):
  F: 50 features → fully complex (increased from 20)
     Industrial parts (engine blocks, manifolds) commonly have 30-50 features.
     20 was too aggressive — it saturated for moderately complex parts.
  W: 10 severity-weighted warnings → fully complex
  S: 6 setups → fully complex (6-sided prismatic machining)
  T: 8 tool types → fully complex
  A: 5 inaccessible features → fully complex

CLASSIFICATION THRESHOLDS
=========================
  • < 0.3  → LOW    (simple prismatic, few features, 1-2 setups)
  • < 0.7  → MEDIUM (moderate features, 2-3 setups)
  • ≥ 0.7  → HIGH   (complex geometry, many setups)

SETUP ESTIMATION LOGIC
========================
The setup count is estimated by counting distinct accessibility direction
clusters. Each unique tool approach direction requires a separate clamping
orientation:
  • (0,0,-1) and (0,0,+1) are DIFFERENT setups (top vs bottom)
  • (1,0,0) and (-1,0,0) are DIFFERENT setups (left vs right)
  • Minimum setup count = 1 (every part needs at least one setup)

When no features are present, setups are estimated from face normal
clusters divided by 2 (opposing normals ≈ same setup when flipped).

ENGINEERING RULES
=================
  • Pure function — no side effects, no DB writes
  • Uses partial report data — tolerant of missing fields
  • Score is always explicitly clamped to [0.0, 1.0]
  • Level is derived deterministically from score
  • All vectors normalized before direction comparison
  • Guard divide-by-zero in all normalization steps
  • Tolerance = 1e-6 for all float comparisons
"""

from __future__ import annotations

import logging
import math
import time

from cad_worker.schemas import (
    ComplexityScore,
    FeatureSpatial,
    ManufacturabilityAnalysis,
    TopologyGraph,
)

logger = logging.getLogger("cad_worker.complexity_scorer")

_TOLERANCE = 1e-6

# ── Normalization saturation maxima ─────────────────────────────────────────
# Calibrated against industrial part complexity surveys.
_MAX_FEATURES = 50          # Typical complex part: 30-50 features
_MAX_SEVERITY_WEIGHT = 10.0 # Weighted sum of DFM warnings
_MAX_SETUPS = 6             # 6-sided prismatic machining
_MAX_TOOL_TYPES = 8         # Distinct (type, diameter) combinations
_MAX_INACCESSIBLE = 5       # Features requiring 5-axis or indexing

# ── Component weights (must sum to 1.0) ─────────────────────────────────────
# Feature count dominates because it directly drives cycle time and toolpath.
_W_FEATURES = 0.3
_W_WARNINGS = 0.2
_W_SETUPS = 0.2
_W_TOOLS = 0.2
_W_ACCESSIBILITY = 0.1

# Verify weight sum at import time
assert abs(
    _W_FEATURES + _W_WARNINGS + _W_SETUPS + _W_TOOLS + _W_ACCESSIBILITY - 1.0
) < _TOLERANCE, "Component weights must sum to 1.0"

# ── Severity weight mapping ─────────────────────────────────────────────────
# Higher severity → higher weight contribution to complexity.
_SEVERITY_WEIGHTS = {
    "LOW": 0.5,
    "MEDIUM": 1.0,
    "HIGH": 2.0,
}

# ── Accessibility alignment threshold ──────────────────────────────────────
# max(|component|) < this → feature is inaccessible from standard axes
_ACCESSIBILITY_THRESHOLD = 0.9


def compute_complexity(
    features: list[FeatureSpatial],
    manufacturability: ManufacturabilityAnalysis,
    topology_graph: TopologyGraph,
) -> ComplexityScore:
    """
    Compute normalized machining complexity score.

    The score aggregates multiple dimensions of manufacturing difficulty:
    feature count, warning severity, estimated setup count, tool diversity,
    and accessibility constraints.

    Args:
        features: Spatially-mapped features.
        manufacturability: Manufacturability analysis with warnings.
        topology_graph: Topology graph for setup estimation.

    Returns:
        ComplexityScore with normalized value [0,1] and level classification.
    """
    t_start = time.monotonic()

    # ── 1. Feature count (F) ────────────────────────────────────────────
    f_raw = len(features)
    f_norm = _normalize(f_raw, _MAX_FEATURES)

    # ── 2. Warning severity weight (W) ──────────────────────────────────
    # Sum severity-weighted warnings: HIGH=2, MEDIUM=1, LOW=0.5
    w_raw = sum(
        _SEVERITY_WEIGHTS.get(w.severity, 1.0)
        for w in manufacturability.warnings
    )
    w_norm = _normalize(w_raw, _MAX_SEVERITY_WEIGHT)

    # ── 3. Estimated setup count (S) ────────────────────────────────────
    s_raw = _estimate_setups(features, topology_graph)
    s_norm = _normalize(s_raw, _MAX_SETUPS)

    # ── 4. Tool diversity estimate (T) ──────────────────────────────────
    t_raw = _estimate_tool_diversity(features)
    t_norm = _normalize(t_raw, _MAX_TOOL_TYPES)

    # ── 5. Accessibility penalty (A) ────────────────────────────────────
    # Count features whose accessibility direction is not aligned with
    # any principal axis — these require indexing or 5-axis.
    a_raw = 0
    for f in features:
        ax = f.accessibility_direction
        # Normalize before checking alignment
        mag = math.sqrt(ax[0] ** 2 + ax[1] ** 2 + ax[2] ** 2)
        if mag < _TOLERANCE:
            a_raw += 1  # Degenerate direction → penalize
            continue
        max_component = max(abs(ax[0]), abs(ax[1]), abs(ax[2])) / mag
        if max_component < _ACCESSIBILITY_THRESHOLD:
            a_raw += 1
    a_norm = _normalize(a_raw, _MAX_INACCESSIBLE)

    # ── Weighted sum ────────────────────────────────────────────────────
    score = (
        _W_FEATURES * f_norm
        + _W_WARNINGS * w_norm
        + _W_SETUPS * s_norm
        + _W_TOOLS * t_norm
        + _W_ACCESSIBILITY * a_norm
    )

    # Explicit clamping to [0.0, 1.0]
    score = max(0.0, min(1.0, round(score, 4)))

    # Classify
    if score < 0.3:
        level = "LOW"
    elif score < 0.7:
        level = "MEDIUM"
    else:
        level = "HIGH"

    elapsed_ms = (time.monotonic() - t_start) * 1000
    logger.info(
        f"Complexity: {score} ({level}) in {elapsed_ms:.1f}ms — "
        f"F={f_raw}({f_norm:.2f}) W={w_raw:.1f}({w_norm:.2f}) "
        f"S={s_raw}({s_norm:.2f}) T={t_raw}({t_norm:.2f}) "
        f"A={a_raw}({a_norm:.2f})"
    )

    return ComplexityScore(value=score, level=level)


def _normalize(value: float, max_value: float) -> float:
    """
    Normalize a value to [0.0, 1.0] using saturation.

    Formula: min(value / max_value, 1.0)
    Guard: if max_value ≤ 0, returns 0.0 (prevents divide-by-zero).
    """
    if max_value <= _TOLERANCE:
        return 0.0
    return min(value / max_value, 1.0)


def _estimate_setups(
    features: list[FeatureSpatial],
    topology_graph: TopologyGraph,
) -> int:
    """
    Estimate the number of machining setups required.

    Method: count distinct accessibility direction clusters.
    Each unique tool approach direction requires a separate setup.

    Direction snapping: each accessibility vector is snapped to its
    nearest principal axis (±X, ±Y, ±Z). Two features with the same
    snapped direction can be machined in the same setup.

    Minimum: 1 (every part needs at least one setup).
    """
    if not features:
        # No features → estimate from face normals
        # Count distinct normal directions, divide by 2
        # (opposing normals = same setup when part is flipped)
        if not topology_graph.faces:
            return 1
        normal_clusters: set[tuple[int, int, int]] = set()
        for face in topology_graph.faces:
            snapped = _snap_to_principal(face.normal)
            normal_clusters.add(snapped)
        return max(1, len(normal_clusters) // 2)

    # Count distinct snapped accessibility directions
    access_clusters: set[tuple[int, int, int]] = set()
    for feat in features:
        snapped = _snap_to_principal(feat.accessibility_direction)
        access_clusters.add(snapped)

    return max(1, len(access_clusters))


def _snap_to_principal(
    direction: tuple[float, float, float],
) -> tuple[int, int, int]:
    """
    Snap a direction vector to the nearest principal axis.

    Returns (-1, 0, 1) for each component, representing the
    sign of the dominant axis. The dominant axis is the one
    with the largest absolute component.

    Example: (0.1, -0.3, 0.9) → (0, 0, 1)  (dominant = +Z)
    Example: (0.0, -0.95, 0.1) → (0, -1, 0) (dominant = -Y)
    """
    abs_vals = [abs(direction[0]), abs(direction[1]), abs(direction[2])]
    max_val = max(abs_vals)
    if max_val < _TOLERANCE:
        return (0, 0, -1)  # Default: -Z (top-down approach)
    max_idx = abs_vals.index(max_val)
    result = [0, 0, 0]
    result[max_idx] = 1 if direction[max_idx] >= 0 else -1
    return (result[0], result[1], result[2])


def _estimate_tool_diversity(features: list[FeatureSpatial]) -> int:
    """
    Estimate the number of distinct cutting tools needed.

    Groups features by (type, diameter_bucket). Each unique combination
    likely requires a different tool.

    Diameter bucketing: round to nearest 1mm to group similar sizes.
    Example: ∅9.5mm and ∅10.0mm holes → same bucket (10mm).

    Guard: None diameter → bucket 0 (feature type alone determines tool).
    """
    tool_keys: set[tuple[str, int]] = set()

    for feat in features:
        if feat.diameter is not None and feat.diameter > _TOLERANCE:
            diameter_bucket = round(feat.diameter)
        else:
            diameter_bucket = 0
        tool_keys.add((feat.type, diameter_bucket))

    return len(tool_keys)
