"""
Database service for CAD Worker.

Handles writing geometry results, feature results, intelligence reports,
and updating model status. No authentication logic. No API routes.
Pure DB operations.

TRANSACTION GUARANTEES
======================
Each function uses its own async session. The intelligence report and
its denormalized columns are persisted in a SINGLE transaction — if the
commit fails, neither the JSONB nor the columns are written, preventing
inconsistency.

DATA FLOW
=========
  save_geometry_result() → Creates ModelGeometry row (step 6 in worker)
  save_features()        → Creates ModelFeature rows (step 6b in worker)
  save_intelligence_report() → Updates ModelGeometry with:
    • manufacturing_intelligence_report (JSONB)
    • intelligence_ready = True
    • intelligence_partial (from engine_status)
    • Denormalized columns: stock_type, complexity_*, counts, engine_status
  update_model_status()  → Sets CADModel.status (step 8 in worker)
"""

from __future__ import annotations

import logging

from sqlalchemy import select, delete

from shared.db import async_session_factory
from cad_service.models import CADModel
from cad_worker.models import ModelGeometry, ModelFeature
from cad_worker.schemas import GeometryResult, FeatureResult

logger = logging.getLogger("cad_worker.db_service")


async def save_geometry_result(model_id: str, result: GeometryResult) -> str:
    """
    Persist a GeometryResult to the model_geometry table.

    If a geometry record already exists for this model_id, it is replaced
    (idempotent reprocessing).

    Returns:
        The UUID of the saved ModelGeometry record.
    """
    async with async_session_factory() as session:
        # Check for existing geometry record (idempotent)
        existing = await session.execute(
            select(ModelGeometry).where(ModelGeometry.model_id == model_id)
        )
        old_record = existing.scalar_one_or_none()
        if old_record:
            logger.info(f"[{model_id}] Replacing existing geometry record")
            await session.delete(old_record)
            await session.flush()

        geometry = ModelGeometry(
            model_id=model_id,
            geometry_type=result.geometry_type,
            bounding_box=result.bounding_box,
            volume=result.volume,
            surface_area=result.surface_area,
            planar_faces=result.planar_faces,
            cylindrical_faces=result.cylindrical_faces,
            conical_faces=result.conical_faces,
            spherical_faces=result.spherical_faces,
            feature_ready=result.feature_ready,
        )
        session.add(geometry)
        await session.commit()
        logger.info(
            f"[{model_id}] Geometry saved: type={result.geometry_type}, "
            f"feature_ready={result.feature_ready}"
        )
        return geometry.id


async def update_model_status(
    model_id: str,
    new_status: str,
    gltf_path: str | None = None,
) -> None:
    """
    Update the CADModel status (and optionally gltf_path) in the database.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(CADModel).where(CADModel.id == model_id)
        )
        model = result.scalar_one_or_none()

        if not model:
            logger.error(f"[{model_id}] Model not found in DB — cannot update status")
            return

        model.status = new_status
        if gltf_path is not None:
            model.gltf_path = gltf_path

        await session.commit()
        logger.info(f"[{model_id}] DB status updated to {new_status}")


async def save_features(
    model_id: str, features: list[FeatureResult]
) -> list[str]:
    """
    Persist detected features to the model_features table.

    Clears any existing features for this model_id first (idempotent).

    Returns:
        List of UUIDs for the saved ModelFeature records.
    """
    if not features:
        logger.info(f"[{model_id}] No features to save")
        return []

    async with async_session_factory() as session:
        # Clear existing features (idempotent reprocessing)
        await session.execute(
            delete(ModelFeature).where(ModelFeature.model_id == model_id)
        )
        await session.flush()

        saved_ids: list[str] = []
        for fr in features:
            record = ModelFeature(
                model_id=model_id,
                type=fr.type,
                dimensions=fr.dimensions,
                depth=fr.depth,
                diameter=fr.diameter,
                axis=fr.axis,
                tolerance=fr.tolerance,
                surface_finish=fr.surface_finish,
                confidence=fr.confidence,
            )
            session.add(record)
            await session.flush()
            saved_ids.append(record.id)

        await session.commit()
        logger.info(
            f"[{model_id}] {len(saved_ids)} features saved to DB"
        )
        return saved_ids


async def save_intelligence_report(
    model_id: str,
    report_dict: dict,
    engine_status: dict | None = None,
) -> None:
    """
    Persist the ManufacturingGeometryReport and denormalized columns.

    Updates the existing ModelGeometry record (created by save_geometry_result)
    in a SINGLE transaction:
      1. manufacturing_intelligence_report = full JSONB
      2. intelligence_ready = True
      3. intelligence_partial = True if any engine FAILED
      4. Denormalized columns extracted from the JSONB

    Args:
        model_id: UUID string of the CAD model.
        report_dict: ManufacturingGeometryReport serialized as dict
                     (via .model_dump(mode='json')).
        engine_status: Optional engine-by-engine status dict from orchestrator.
                       Keys: engine names, values: "OK" or "FAILED: ..."
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(ModelGeometry).where(ModelGeometry.model_id == model_id)
        )
        geometry = result.scalar_one_or_none()

        if not geometry:
            logger.error(
                f"[{model_id}] No ModelGeometry record found — "
                f"cannot save intelligence report"
            )
            return

        # ── 1. Full JSONB report ────────────────────────────────────────
        geometry.manufacturing_intelligence_report = report_dict
        geometry.intelligence_ready = True

        # ── 2. Partial report flag ──────────────────────────────────────
        # If any engine has "FAILED" in its status → partial report
        is_partial = False
        if engine_status:
            is_partial = any("FAILED" in v for v in engine_status.values())
        geometry.intelligence_partial = is_partial

        # ── 3. Denormalized query columns ───────────────────────────────
        # Extract from the report_dict to avoid JSONB path queries later.
        # Each extraction is guarded with .get() to handle partial reports.

        # Stock type
        stock_rec = report_dict.get("stock_recommendation")
        if stock_rec and isinstance(stock_rec, dict):
            geometry.stock_type = stock_rec.get("type")

        # Complexity
        complexity = report_dict.get("complexity_score")
        if complexity and isinstance(complexity, dict):
            geometry.complexity_value = complexity.get("value")
            geometry.complexity_level = complexity.get("level")

        # Feature count
        features = report_dict.get("features")
        if features and isinstance(features, list):
            geometry.intelligence_feature_count = len(features)

        # Warning count
        mfg = report_dict.get("manufacturability_analysis")
        if mfg and isinstance(mfg, dict):
            warnings = mfg.get("warnings")
            if warnings and isinstance(warnings, list):
                geometry.intelligence_warning_count = len(warnings)

        # Engine status
        geometry.intelligence_engine_status = engine_status

        # ── Single commit for all columns ───────────────────────────────
        await session.commit()

        logger.info(
            f"[{model_id}] Intelligence report saved: "
            f"stock={geometry.stock_type}, "
            f"complexity={geometry.complexity_value} ({geometry.complexity_level}), "
            f"features={geometry.intelligence_feature_count}, "
            f"warnings={geometry.intelligence_warning_count}, "
            f"partial={is_partial}"
        )
