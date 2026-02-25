"""
Database service for CAD Worker.

Handles writing geometry results and updating model status.
No authentication logic. No API routes. Pure DB operations.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from shared.db import async_session_factory
from cad_service.models import CADModel
from cad_worker.models import ModelGeometry
from cad_worker.schemas import GeometryResult

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
