"""
CAD file processor.

Processing pipeline:
  1. Download the CAD file from storage
  2. Parse the geometry (STL via trimesh; STEP/IGES via OpenCascade future)
  3. Export to GLB (binary glTF) format
  4. Upload GLB back to storage
  5. Update DB status to READY

Supported formats:
  - STL: fully processed via trimesh — viewer shows the actual uploaded mesh
  - STEP / IGES / Parasolid: require OpenCascade (not yet installed),
    so they currently generate a placeholder cube with a log warning.
"""

import asyncio
import io
import logging

import trimesh

from sqlalchemy import select

from shared.config import get_settings
from shared.db import async_session_factory
from shared.storage import save_file, read_file, file_exists
from cad_service.models import CADModel

logger = logging.getLogger("cad_worker.processor")
settings = get_settings()

# Formats that trimesh can parse natively
_TRIMESH_FORMATS = {"STL", "OBJ", "PLY", "OFF", "GLB", "GLTF"}


async def process_model(model_id: str, gcs_path: str) -> None:
    """
    Process a single CAD model.

    Steps:
      1. Look up the file format in the DB
      2. Verify source CAD file in storage
      3. Convert to GLB (binary glTF)
      4. Update DB status to READY
    """
    logger.info(f"Processing model {model_id} from {gcs_path}")

    try:
        # ── Step 1: Get file format from DB ───────────────────────────────
        file_format = await _get_model_format(model_id)

        # ── Step 2: Verify & read source file ────────────────────────────
        logger.info(f"[{model_id}] Verifying CAD file in storage...")
        if not file_exists(gcs_path):
            raise FileNotFoundError(f"Source CAD file not found: {gcs_path}")
        source_data = await read_file(gcs_path)
        logger.info(f"[{model_id}] CAD file verified — {len(source_data)} bytes")

        # ── Step 3: Convert to GLB ────────────────────────────────────────
        glb_path = f"processed/{model_id}/model.glb"
        logger.info(f"[{model_id}] Converting to GLB...")
        glb_data = await _convert_to_glb(model_id, source_data, file_format, gcs_path)
        await save_file(glb_path, glb_data)
        logger.info(f"[{model_id}] GLB saved: {glb_path} ({len(glb_data)} bytes)")

        # ── Step 4: Update DB status ──────────────────────────────────────
        await _update_model_status(model_id, "READY", gltf_path=glb_path)
        logger.info(f"[{model_id}] Processing complete — status set to READY")

    except Exception as e:
        logger.error(f"[{model_id}] Processing failed: {e}")
        await _update_model_status(model_id, "FAILED")
        raise


# ── Processing implementations ────────────────────────────────────────────────

async def _get_model_format(model_id: str) -> str:
    """Look up the file format from the database."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(CADModel.file_format).where(CADModel.id == model_id)
        )
        fmt = result.scalar_one_or_none()
        if not fmt:
            raise ValueError(f"Model {model_id} not found in DB")
        return fmt.upper()


async def _convert_to_glb(
    model_id: str,
    source_data: bytes,
    file_format: str,
    gcs_path: str,
) -> bytes:
    """
    Convert a CAD file to GLB format.

    For formats supported by trimesh (STL, OBJ, PLY, etc.), the actual
    uploaded geometry is parsed and re-exported as GLB.

    For formats that need OpenCascade (STEP, IGES, Parasolid), a placeholder
    cube is generated until OCP is installed.
    """
    if file_format in _TRIMESH_FORMATS:
        return await _trimesh_to_glb(model_id, source_data, file_format)
    else:
        logger.warning(
            f"[{model_id}] Format {file_format} requires OpenCascade — "
            f"generating placeholder cube. Install OCP for real conversion."
        )
        return _build_placeholder_glb()


async def _trimesh_to_glb(
    model_id: str,
    data: bytes,
    file_format: str,
) -> bytes:
    """
    Parse geometry with trimesh and export as GLB.
    Runs the CPU-heavy parsing in a thread to avoid blocking the event loop.
    """
    def _do_convert() -> bytes:
        # trimesh.load expects a file-like object + file_type hint
        file_type = file_format.lower()
        mesh_or_scene = trimesh.load(
            io.BytesIO(data),
            file_type=file_type,
            force="mesh",  # collapse Scene to single mesh if needed
        )

        if isinstance(mesh_or_scene, trimesh.Scene):
            # Already a scene — just export
            scene = mesh_or_scene
        elif isinstance(mesh_or_scene, trimesh.Trimesh):
            scene = trimesh.Scene(mesh_or_scene)
        else:
            raise ValueError(f"Unexpected trimesh result type: {type(mesh_or_scene)}")

        logger.info(
            f"[{model_id}] Mesh loaded: "
            f"{sum(len(g.faces) for g in scene.geometry.values() if hasattr(g, 'faces'))} faces, "
            f"{sum(len(g.vertices) for g in scene.geometry.values() if hasattr(g, 'vertices'))} vertices"
        )

        return scene.export(file_type="glb")

    # Offload CPU work to a thread
    return await asyncio.to_thread(_do_convert)


def _build_placeholder_glb() -> bytes:
    """
    Build a minimal placeholder GLB (unit cube) for formats that
    can't yet be parsed (STEP, IGES, Parasolid).
    Uses trimesh for consistent GLB output.
    """
    box = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    scene = trimesh.Scene(box)
    return scene.export(file_type="glb")


async def _update_model_status(
    model_id: str,
    new_status: str,
    gltf_path: str | None = None,
) -> None:
    """
    Update the model's status in the database.
    The worker shares the DB session factory with CAD Service
    (same service boundary — models table is owned by CAD domain).
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(CADModel).where(CADModel.id == model_id)
        )
        model = result.scalar_one_or_none()
        if model:
            model.status = new_status
            if gltf_path:
                model.gltf_path = gltf_path
            await session.commit()
            logger.info(f"[{model_id}] DB status updated to {new_status}")
        else:
            logger.error(f"[{model_id}] Model not found in DB")
