"""
Intelligence Adapter — converts ManufacturingGeometryReport → PlanningContext.

Pure translation layer. No planning logic. No mutations.
Converts intelligence report data into the typed PlanningContext schema
consumed by all downstream planning modules.
"""

from __future__ import annotations

import logging
from typing import Any

from ai_service.schemas.planning_context import (
    PlanningContext,
    FeatureContext,
    GeometryMetadata,
    ManufacturabilityFlag,
    StockRecommendation,
)
from ai_service.ingestion.intelligence_client import IntelligencePayload

logger = logging.getLogger("ai_service.ingestion.intelligence_adapter")


def adapt_intelligence(
    payload: IntelligencePayload,
    *,
    material: str,
    machine_type: str,
    optimization_goal: str = "BALANCED",
) -> PlanningContext:
    """
    Convert an IntelligencePayload into a PlanningContext.

    Args:
        payload:           Validated intelligence response.
        material:          Workpiece material string.
        machine_type:      MILLING_3AXIS | LATHE.
        optimization_goal: MINIMIZE_TIME | MINIMIZE_TOOL_CHANGES | BALANCED.

    Returns:
        PlanningContext ready for base plan generation.
    """
    report = payload.manufacturing_geometry_report

    # ── Features ─────────────────────────────────────────────────────────
    features: list[FeatureContext] = []
    for feat in report.get("features", []):
        if not isinstance(feat, dict):
            continue

        # Convert axis from list/tuple to dict
        axis_raw = feat.get("axis_direction")
        axis_dict: dict[str, float] | None = None
        if axis_raw and isinstance(axis_raw, (list, tuple)) and len(axis_raw) >= 3:
            axis_dict = {"x": axis_raw[0], "y": axis_raw[1], "z": axis_raw[2]}

        # Build dimensions dict
        dimensions: dict[str, Any] = {}
        for key in ("diameter", "depth", "width", "length"):
            if feat.get(key) is not None:
                dimensions[key] = feat[key]

        features.append(FeatureContext(
            id=feat.get("id", ""),
            type=feat.get("type", ""),
            confidence=feat.get("confidence", 1.0),
            dimensions=dimensions,
            depth=feat.get("depth"),
            diameter=feat.get("diameter"),
            axis=axis_dict,
            accessibility_direction=feat.get("accessibility_direction"),
            hole_subtype=feat.get("hole_subtype"),
            machining_class=feat.get("machining_class"),
            requires_flip=feat.get("requires_flip", False),
            requires_multi_axis=feat.get("requires_multi_axis", False),
            parent_feature_id=feat.get("parent_feature_id"),
            tolerance=feat.get("tolerance"),
            surface_finish=feat.get("surface_finish"),
            is_through=feat.get("is_through", False),
        ))

    # ── Geometry Metadata ────────────────────────────────────────────────
    geo_summary = report.get("geometry_summary", {})
    topology = report.get("topology_graph", {})
    faces = topology.get("faces", [])

    geometry = GeometryMetadata(
        volume=geo_summary.get("volume", 0.0),
        surface_area=geo_summary.get("surface_area", 0.0),
        bounding_box=geo_summary.get("bounding_box", {}),
        planar_faces=_count_faces(faces, "PLANAR"),
        cylindrical_faces=_count_faces(faces, "CYLINDRICAL"),
        conical_faces=_count_faces(faces, "CONICAL"),
        spherical_faces=_count_faces(faces, "SPHERICAL"),
    )

    # ── Datum ────────────────────────────────────────────────────────────
    datum_candidates = report.get("datum_candidates", {})
    if isinstance(datum_candidates, list):
        # List of candidate dicts — pick the first face_id as primary
        datum_primary = datum_candidates[0].get("face_id") if datum_candidates else None
    elif isinstance(datum_candidates, dict):
        datum_primary = datum_candidates.get("primary")
    else:
        datum_primary = None

    # ── Stock ────────────────────────────────────────────────────────────
    stock_raw = report.get("stock_recommendation", {})
    stock = StockRecommendation(
        form=stock_raw.get("form", "BILLET"),
        dimensions=stock_raw.get("dimensions", {}),
        material_volume=stock_raw.get("material_volume", 0.0),
        stock_volume=stock_raw.get("stock_volume", 0.0),
        material_utilization=stock_raw.get("material_utilization", 0.0),
    )

    # ── Manufacturability Flags ──────────────────────────────────────────
    mfg = report.get("manufacturability_analysis", {})
    flags: list[ManufacturabilityFlag] = []
    for w in mfg.get("warnings", []):
        if isinstance(w, dict):
            flags.append(ManufacturabilityFlag(
                code=w.get("code", "UNKNOWN"),
                severity=w.get("severity", "WARNING"),
                message=w.get("message", ""),
                affected_feature_ids=w.get("affected_feature_ids", []),
            ))

    # ── Complexity ───────────────────────────────────────────────────────
    complexity_score = report.get("complexity_score", {})
    complexity = complexity_score.get("value", 0.0)

    context = PlanningContext(
        model_id=payload.model_id,
        material=material,
        machine_type=machine_type,
        features=features,
        geometry=geometry,
        datum_primary=datum_primary,
        stock=stock,
        manufacturability_flags=flags,
        complexity_score=complexity,
        optimization_goal=optimization_goal,
    )

    logger.info(
        "Adapted intelligence → PlanningContext: features=%d complexity=%.2f flags=%d",
        len(features), complexity, len(flags),
    )
    return context


def _count_faces(faces: list, surface_type: str) -> int:
    """Count faces of a given surface type in the topology graph."""
    return sum(
        1 for f in faces
        if isinstance(f, dict) and f.get("surface_type") == surface_type
    )
