"""
Intelligence Orchestrator — assembles the full ManufacturingGeometryReport.

This is the single entry point for Phase A intelligence generation.
It pipelines all engines in strict order, with dependency-aware fault
isolation and self-validation.

WHY THE WORKER MUST NOT CRASH
==============================
The CAD Worker processes files from a Pub/Sub queue. If the worker
crashes (uncaught exception), the message is re-delivered, potentially
causing an infinite retry loop. The orchestrator guarantees:
  1. Every engine failure is caught, logged, and replaced with safe defaults
  2. The final report always passes Pydantic validation
  3. A partial report (some engines failed) is stored as valid JSONB
  4. The worker continues to the next message

PIPELINE ORDER AND DEPENDENCY GRAPH
=====================================
  1. geometry_summary    ← REQUIRED (halt if fails)
  2. topology_graph      ← REQUIRED for steps 4-8
  3. feature_detection   ← needed by 4
  4. spatial_features    ← needed by 7, 8
  5. stock_recommendation ← depends on 1, 2
  6. datum_candidates     ← depends on 2
  7. manufacturability    ← depends on 2, 4, 6
  8. complexity_score     ← depends on 2, 4, 7

DEPENDENCY-AWARE FAILURE HANDLING
==================================
  • geometry_summary fails → HALT. This is the foundation. Without bbox/volume,
    stock recommendation is meaningless, datum detection has no reference frame,
    and complexity scoring has no normalization anchor.
  • topology_graph fails → SKIP steps 4-8. All downstream engines depend on
    face data, normals, and adjacency. Running them with empty topology produces
    garbage results that waste compute and may mislead the AI Brain.
  • Any other step fails → continue with safe defaults for that step.

SELF-VALIDATION (POST-ASSEMBLY)
================================
After report assembly, validate internal consistency:
  • All feature parent_face_ids exist in topology graph
  • No duplicate face IDs
  • Bounding box dimensions > 0
  • Complexity score in [0, 1]
  • Adjacency references point to valid face IDs
Log warnings for inconsistencies but DO NOT crash.

ENGINEERING RULES
=================
  • Only this module orchestrates the pipeline
  • Only this module calls save to DB (via the caller in worker.py)
  • Each engine is a pure function — no side effects
  • Pydantic validates the final report before returning
  • Safe defaults allow partial reports to be valid
  • Tolerance = 1e-6 for all float comparisons
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from cad_worker.schemas import (
    BoundingBox,
    ComplexityScore,
    DatumCandidates,
    FeatureSpatial,
    GeometrySummary,
    ManufacturabilityAnalysis,
    ManufacturingGeometryReport,
    StockRecommendation,
    TopologyGraph,
)

logger = logging.getLogger("cad_worker.intelligence_orchestrator")

_TOLERANCE = 1e-6


def generate_manufacturing_geometry_report(
    shape,
    model_id: str,
) -> tuple[ManufacturingGeometryReport, dict]:
    """
    Run the full manufacturing intelligence pipeline on a BRep shape.

    This function NEVER raises — all exceptions are caught and logged.
    Failed engines produce safe default values. The returned report
    is always valid Pydantic and ready for JSONB storage.

    Dependency-aware halt logic:
      • geometry_summary failure → pipeline halts, returns defaults-only report
      • topology_graph failure → steps 4-8 skipped (all depend on topology)

    Args:
        shape: A valid OCC TopoDS_Shape.
        model_id: UUID string of the CAD model.

    Returns:
        Tuple of:
          - ManufacturingGeometryReport (always valid, possibly partial)
          - engine_status dict ({engine_name: "OK" | "FAILED: ..." | "SKIPPED ..."})
    """
    pipeline_start = time.monotonic()
    logger.info(f"[{model_id}] Starting manufacturing intelligence pipeline...")

    # ── Default safe values (used when engines fail) ────────────────────
    geometry_summary = GeometrySummary(
        bounding_box=BoundingBox(length=0.0001, width=0.0001, height=0.0001),
        volume=0.0,
        surface_area=0.0,
        center_of_mass=(0.0, 0.0, 0.0),
    )
    topology_graph = TopologyGraph(faces=[], edges=[])
    spatial_features: list[FeatureSpatial] = []
    stock_recommendation = StockRecommendation(
        type="BLOCK",
        length=0.0001,
        width=0.0001,
        height=0.0001,
        allowance_per_face=2.0,
    )
    datum_candidates = DatumCandidates(
        primary="F_001",
        secondary=None,
        tertiary=None,
        reasoning="Datum detection did not run (pipeline error).",
    )
    manufacturability_analysis = ManufacturabilityAnalysis(warnings=[])
    complexity_score = ComplexityScore(value=0.0, level="LOW")

    # Track which engines ran successfully for diagnostics
    engine_status: dict[str, str] = {}

    # ── Step 1: Geometry Summary (REQUIRED — halt if fails) ─────────────
    geometry_ok = False
    try:
        from cad_worker.geometry_engine.geometry_summary import (
            compute_geometry_summary,
        )
        geometry_summary = compute_geometry_summary(shape)
        geometry_ok = True
        engine_status["geometry_summary"] = "OK"
        logger.info(f"[{model_id}] ✓ Geometry summary computed")
    except Exception as e:
        engine_status["geometry_summary"] = f"FAILED: {e}"
        logger.error(
            f"[{model_id}] ✗ Geometry summary FAILED — HALTING pipeline: {e}",
            exc_info=True,
        )

    if not geometry_ok:
        # Geometry summary is the foundation — without it, everything is garbage.
        # Return a defaults-only report immediately.
        elapsed = (time.monotonic() - pipeline_start) * 1000
        logger.warning(
            f"[{model_id}] Pipeline halted: geometry_summary failed. "
            f"Returning defaults-only report. {elapsed:.1f}ms"
        )
        report = _assemble_report(
            model_id, geometry_summary, topology_graph,
            spatial_features, stock_recommendation, datum_candidates,
            manufacturability_analysis, complexity_score,
        )
        _self_validate(model_id, report)
        return report, engine_status

    # ── Step 2: Topology Graph (REQUIRED for steps 4-8) ─────────────────
    topology_ok = False
    try:
        from cad_worker.geometry_engine.topology_graph import (
            build_topology_graph,
        )
        topology_graph = build_topology_graph(shape)
        topology_ok = True
        engine_status["topology_graph"] = "OK"
        logger.info(
            f"[{model_id}] ✓ Topology graph: "
            f"{len(topology_graph.faces)} faces, "
            f"{len(topology_graph.edges)} edges"
        )
    except Exception as e:
        engine_status["topology_graph"] = f"FAILED: {e}"
        logger.error(
            f"[{model_id}] ✗ Topology graph FAILED — "
            f"skipping dependent modules: {e}",
            exc_info=True,
        )

    # ── Step 3: Feature Detection ───────────────────────────────────────
    feature_results = []
    try:
        from cad_worker.geometry_engine.feature_recognition import (
            detect_all_features,
        )
        feature_results = detect_all_features(shape)
        engine_status["feature_detection"] = "OK"
        logger.info(
            f"[{model_id}] ✓ Feature detection: {len(feature_results)} features"
        )
    except Exception as e:
        engine_status["feature_detection"] = f"FAILED: {e}"
        logger.error(
            f"[{model_id}] ✗ Feature detection FAILED: {e}", exc_info=True
        )

    # ── Steps 4-8: Only run if topology graph succeeded ─────────────────
    if topology_ok:
        # Step 4: Spatial Feature Mapping
        try:
            from cad_worker.geometry_engine.spatial_feature_mapper import (
                map_features_spatially,
            )
            spatial_features = map_features_spatially(
                shape, feature_results, topology_graph, geometry_summary
            )
            engine_status["spatial_mapping"] = "OK"
            logger.info(
                f"[{model_id}] ✓ Spatial mapping: {len(spatial_features)} features"
            )
        except Exception as e:
            engine_status["spatial_mapping"] = f"FAILED: {e}"
            logger.error(
                f"[{model_id}] ✗ Spatial feature mapping FAILED: {e}",
                exc_info=True,
            )

        # Step 5: Stock Recommendation
        try:
            from cad_worker.intelligence.stock_recommender import recommend_stock
            stock_recommendation = recommend_stock(geometry_summary, topology_graph)
            engine_status["stock_recommendation"] = "OK"
            logger.info(
                f"[{model_id}] ✓ Stock: {stock_recommendation.type}"
            )
        except Exception as e:
            engine_status["stock_recommendation"] = f"FAILED: {e}"
            logger.error(
                f"[{model_id}] ✗ Stock recommendation FAILED: {e}",
                exc_info=True,
            )

        # Step 6: Datum Detection (moved before enhancement steps)
        try:
            from cad_worker.intelligence.datum_detector import detect_datums
            datum_candidates = detect_datums(topology_graph)
            engine_status["datum_detection"] = "OK"
            logger.info(
                f"[{model_id}] ✓ Datum: primary={datum_candidates.primary}"
            )
        except Exception as e:
            engine_status["datum_detection"] = f"FAILED: {e}"
            logger.error(
                f"[{model_id}] ✗ Datum detection FAILED: {e}", exc_info=True
            )

        # ── Phase B Enhancement Steps (non-critical, wrapped in try/except) ──

        # Step 6a: Hole Classification (classifies HOLE subtypes)
        try:
            from cad_worker.geometry_engine.feature_recognition.hole_classifier import (
                classify_holes,
            )
            spatial_features = classify_holes(
                spatial_features, geometry_summary, topology_graph
            )
            engine_status["hole_classification"] = "OK"
            hole_count = sum(
                1 for f in spatial_features
                if f.type == "HOLE" and f.hole_subtype is not None
            )
            logger.info(
                f"[{model_id}] ✓ Hole classification: {hole_count} holes classified"
            )
        except Exception as e:
            engine_status["hole_classification"] = f"FAILED: {e}"
            logger.error(
                f"[{model_id}] ✗ Hole classification FAILED: {e}",
                exc_info=True,
            )

        # Step 6b: Feature Relationship Mapping
        try:
            from cad_worker.geometry_engine.feature_relationship_mapper import (
                build_feature_relationships,
            )
            spatial_features = build_feature_relationships(
                spatial_features, topology_graph
            )
            engine_status["feature_relationships"] = "OK"
            parent_count = sum(
                1 for f in spatial_features if f.parent_feature_id is not None
            )
            logger.info(
                f"[{model_id}] ✓ Feature relationships: "
                f"{parent_count} parent-child links"
            )
        except Exception as e:
            engine_status["feature_relationships"] = f"FAILED: {e}"
            logger.error(
                f"[{model_id}] ✗ Feature relationship mapping FAILED: {e}",
                exc_info=True,
            )

        # Step 6c: Machining Class Assignment
        try:
            from cad_worker.geometry_engine.machining_class_assigner import (
                assign_machining_classes,
            )
            spatial_features = assign_machining_classes(
                spatial_features, datum_candidates, topology_graph
            )
            engine_status["machining_classification"] = "OK"
            flip_count = sum(1 for f in spatial_features if f.requires_flip)
            multi_count = sum(1 for f in spatial_features if f.requires_multi_axis)
            logger.info(
                f"[{model_id}] ✓ Machining classes: "
                f"{flip_count} flips, {multi_count} multi-axis"
            )
        except Exception as e:
            engine_status["machining_classification"] = f"FAILED: {e}"
            logger.error(
                f"[{model_id}] ✗ Machining class assignment FAILED: {e}",
                exc_info=True,
            )

        # Step 7: Manufacturability Analysis (uses enhanced features + datum)
        try:
            from cad_worker.intelligence.manufacturability_analyzer import analyze
            manufacturability_analysis = analyze(
                spatial_features, topology_graph, datum_candidates
            )
            engine_status["manufacturability"] = "OK"
            logger.info(
                f"[{model_id}] ✓ Manufacturability: "
                f"{len(manufacturability_analysis.warnings)} warnings"
            )
        except Exception as e:
            engine_status["manufacturability"] = f"FAILED: {e}"
            logger.error(
                f"[{model_id}] ✗ Manufacturability FAILED: {e}",
                exc_info=True,
            )

        # Step 8: Complexity Score
        try:
            from cad_worker.intelligence.complexity_scorer import compute_complexity
            complexity_score = compute_complexity(
                spatial_features, manufacturability_analysis, topology_graph
            )
            engine_status["complexity_score"] = "OK"
            logger.info(
                f"[{model_id}] ✓ Complexity: "
                f"{complexity_score.value} ({complexity_score.level})"
            )
        except Exception as e:
            engine_status["complexity_score"] = f"FAILED: {e}"
            logger.error(
                f"[{model_id}] ✗ Complexity scoring FAILED: {e}",
                exc_info=True,
            )
    else:
        # Topology failed — mark all dependent engines as skipped
        for key in ["spatial_mapping", "stock_recommendation",
                     "datum_detection", "hole_classification",
                     "feature_relationships", "machining_classification",
                     "manufacturability", "complexity_score"]:
            engine_status[key] = "SKIPPED (topology_graph failed)"
        logger.warning(
            f"[{model_id}] Steps 4-8 skipped due to topology_graph failure"
        )

    # ── Assemble and validate report ────────────────────────────────────
    report = _assemble_report(
        model_id, geometry_summary, topology_graph,
        spatial_features, stock_recommendation, datum_candidates,
        manufacturability_analysis, complexity_score,
    )

    # ── Self-validation ─────────────────────────────────────────────────
    _self_validate(model_id, report)

    # ── Pipeline summary ────────────────────────────────────────────────
    elapsed = (time.monotonic() - pipeline_start) * 1000

    ok_count = sum(1 for v in engine_status.values() if v == "OK")
    total_count = len(engine_status)
    failed_engines = [k for k, v in engine_status.items() if "FAILED" in v]

    logger.info(
        f"[{model_id}] Pipeline complete in {elapsed:.1f}ms: "
        f"{ok_count}/{total_count} engines OK"
        + (f", FAILED: {failed_engines}" if failed_engines else "")
    )

    return report, engine_status


def _assemble_report(
    model_id: str,
    geometry_summary: GeometrySummary,
    topology_graph: TopologyGraph,
    spatial_features: list[FeatureSpatial],
    stock_recommendation: StockRecommendation,
    datum_candidates: DatumCandidates,
    manufacturability_analysis: ManufacturabilityAnalysis,
    complexity_score: ComplexityScore,
) -> ManufacturingGeometryReport:
    """
    Assemble the final report with Pydantic validation.

    If Pydantic validation fails, it indicates a bug in our safe defaults
    — this should never happen in production and is logged as ERROR.
    """
    report = ManufacturingGeometryReport(
        model_id=UUID(model_id),
        geometry_summary=geometry_summary,
        topology_graph=topology_graph,
        features=spatial_features,
        stock_recommendation=stock_recommendation,
        datum_candidates=datum_candidates,
        manufacturability_analysis=manufacturability_analysis,
        complexity_score=complexity_score,
    )

    # Pydantic v2 round-trip validation
    try:
        ManufacturingGeometryReport.model_validate(report.model_dump())
        logger.info(f"[{model_id}] ✓ Report Pydantic validation passed")
    except Exception as e:
        logger.error(
            f"[{model_id}] ✗ Report Pydantic validation FAILED "
            f"— this is a code bug: {e}",
            exc_info=True,
        )

    return report


def _self_validate(
    model_id: str,
    report: ManufacturingGeometryReport,
) -> None:
    """
    Post-assembly consistency checks.

    These do NOT crash the pipeline — they log warnings for
    inconsistencies that indicate data quality issues.
    """
    issues: list[str] = []
    bbox = report.geometry_summary.bounding_box

    # 1. Bounding box dimensions > 0
    if bbox.length < _TOLERANCE or bbox.width < _TOLERANCE or bbox.height < _TOLERANCE:
        issues.append(
            f"Bounding box near-zero: {bbox.length}x{bbox.width}x{bbox.height}"
        )

    # 2. Complexity score in [0, 1]
    if report.complexity_score.value < 0.0 or report.complexity_score.value > 1.0:
        issues.append(
            f"Complexity score out of range: {report.complexity_score.value}"
        )

    # 3. No duplicate face IDs
    face_ids = [f.id for f in report.topology_graph.faces]
    if len(face_ids) != len(set(face_ids)):
        dupes = [fid for fid in face_ids if face_ids.count(fid) > 1]
        issues.append(f"Duplicate face IDs: {set(dupes)}")

    # 4. All feature parent_face_ids exist in topology graph
    valid_ids = set(face_ids)
    for feat in report.features:
        if feat.parent_face_id not in valid_ids and valid_ids:
            issues.append(
                f"Feature {feat.id}: parent_face_id={feat.parent_face_id} "
                f"not in topology graph"
            )

    # 5. Adjacency references point to valid face IDs
    for fn in report.topology_graph.faces:
        for adj_id in fn.adjacent_faces:
            if adj_id not in valid_ids:
                issues.append(
                    f"Face {fn.id}: adjacency ref {adj_id} not in topology"
                )

    # 6. Datum face ID exists
    if valid_ids:
        if report.datum_candidates.primary not in valid_ids:
            issues.append(
                f"Primary datum {report.datum_candidates.primary} "
                f"not in topology graph"
            )

    if issues:
        logger.warning(
            f"[{model_id}] Self-validation found {len(issues)} issues:\n"
            + "\n".join(f"  • {issue}" for issue in issues)
        )
    else:
        logger.info(f"[{model_id}] ✓ Self-validation: all checks passed")
