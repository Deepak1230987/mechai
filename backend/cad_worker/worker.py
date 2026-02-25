"""
CAD Worker — message processing orchestrator.

This is the single entry point called by the subscriber (Pub/Sub or DB poller).

Pipeline:
  1. Parse model_id + storage_path from message
  2. Download CAD file from storage
  3. Detect file extension → select geometry engine via factory
  4. Extract deterministic geometry metrics
  5. Save ModelGeometry record to DB
  6. Generate glTF (reuse existing trimesh converter)
  7. Upload glTF to storage
  8. Update model status to READY

On failure:
  - Update model.status = FAILED
  - Log full error
  - Do NOT crash the worker process

No authentication logic.
No AI logic.
No RFQ logic.
No API routes.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from pathlib import Path

import trimesh

from shared.config import get_settings
from shared.storage import save_file
from cad_worker.geometry_engine import get_engine, UnsupportedFormatError
from cad_worker.services.db_service import save_geometry_result, update_model_status
from cad_worker.services.storage_service import download_file

logger = logging.getLogger("cad_worker.worker")
settings = get_settings()

# Extensions that the existing trimesh converter can handle for glTF export
_TRIMESH_NATIVE = {".stl", ".obj", ".ply", ".off", ".glb", ".gltf"}

# Validated extensions (MVP)
_VALID_EXTENSIONS = {".step", ".stp", ".iges", ".igs", ".stl"}


async def process_message(model_id: str, storage_path: str) -> None:
    """
    Process a single CAD model triggered by Pub/Sub or DB poller.

    This function NEVER raises — all exceptions are caught, logged,
    and result in model.status = FAILED.
    """
    start_time = time.monotonic()
    logger.info(f"[{model_id}] Processing started — path: {storage_path}")

    try:
        # ── 1. Validate inputs ───────────────────────────────────────────
        if not model_id or not storage_path:
            raise ValueError("model_id and storage_path are required")

        # ── 2. Extract and validate file extension ───────────────────────
        ext = Path(storage_path).suffix.lower()
        if ext not in _VALID_EXTENSIONS:
            raise UnsupportedFormatError(ext)
        logger.info(f"[{model_id}] File extension: {ext}")

        # ── 3. Download file from storage ────────────────────────────────
        local_path = await download_file(storage_path)
        logger.info(f"[{model_id}] File downloaded to: {local_path}")

        # ── 4. Select geometry engine ────────────────────────────────────
        engine = get_engine(ext)

        # ── 5. Extract geometry (CPU-bound — run in thread) ──────────────
        geometry_result = await asyncio.to_thread(
            engine.extract_geometry, str(local_path)
        )
        logger.info(
            f"[{model_id}] Geometry extracted: "
            f"type={geometry_result.geometry_type}, "
            f"vol={geometry_result.volume}, "
            f"sa={geometry_result.surface_area}"
        )

        # ── 6. Save geometry to DB ───────────────────────────────────────
        geometry_id = await save_geometry_result(model_id, geometry_result)
        logger.info(f"[{model_id}] Geometry record saved: {geometry_id}")

        # ── 7. Generate glTF ─────────────────────────────────────────────
        glb_data = await _generate_gltf(model_id, local_path, ext)
        glb_path = f"processed/{model_id}/model.glb"
        await save_file(glb_path, glb_data)
        logger.info(f"[{model_id}] glTF saved: {glb_path} ({len(glb_data)} bytes)")

        # ── 8. Update model to READY ─────────────────────────────────────
        await update_model_status(model_id, "READY", gltf_path=glb_path)

        elapsed = time.monotonic() - start_time
        logger.info(
            f"[{model_id}] Processing complete in {elapsed:.2f}s — status: READY"
        )

    except Exception as e:
        elapsed = time.monotonic() - start_time
        logger.error(
            f"[{model_id}] Processing FAILED after {elapsed:.2f}s: {e}",
            exc_info=True,
        )
        try:
            await update_model_status(model_id, "FAILED")
        except Exception as db_err:
            logger.error(
                f"[{model_id}] Failed to update status to FAILED: {db_err}"
            )

    finally:
        # Clean up temp file in production mode
        if settings.ENV == "production":
            try:
                local_path_obj = Path(local_path)  # type: ignore[possibly-undefined]
                if local_path_obj.exists() and str(local_path_obj).startswith(
                    os.path.join(os.sep, "tmp")
                ):
                    local_path_obj.unlink()
                    logger.debug(f"[{model_id}] Temp file cleaned up")
            except Exception:
                pass  # Best-effort cleanup


# ── glTF generation ──────────────────────────────────────────────────────────

async def _generate_gltf(
    model_id: str, local_path: Path, ext: str
) -> bytes:
    """
    Generate GLB (binary glTF) from the CAD file.

    For STL:  trimesh parses and re-exports directly.
    For STEP/IGES: uses OCP tessellation → trimesh → GLB.
    """
    if ext in _TRIMESH_NATIVE:
        return await _trimesh_to_glb(model_id, local_path, ext)
    else:
        return await _brep_to_glb(model_id, local_path)


async def _trimesh_to_glb(model_id: str, local_path: Path, ext: str) -> bytes:
    """Convert a mesh file to GLB using trimesh."""
    def _do_convert() -> bytes:
        mesh = trimesh.load(
            str(local_path),
            file_type=ext.lstrip("."),
            force="mesh",
        )
        if isinstance(mesh, trimesh.Trimesh):
            scene = trimesh.Scene(mesh)
        elif isinstance(mesh, trimesh.Scene):
            scene = mesh
        else:
            raise ValueError(f"Unexpected type from trimesh: {type(mesh)}")
        return scene.export(file_type="glb")

    return await asyncio.to_thread(_do_convert)


async def _brep_to_glb(model_id: str, local_path: Path) -> bytes:
    """
    Convert a BRep file (STEP/IGES) to GLB via OCP tessellation.

    Pipeline: OCC shape → tessellate → trimesh → GLB
    """
    def _do_convert() -> bytes:
        try:
            from OCP.STEPControl import STEPControl_Reader
            from OCP.IGESControl import IGESControl_Reader
            from OCP.IFSelect import IFSelect_RetDone
            from OCP.BRepMesh import BRepMesh_IncrementalMesh
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE
            from OCP.TopoDS import TopoDS
            from OCP.BRep import BRep_Tool
            from OCP.TopLoc import TopLoc_Location
            import numpy as np

            ext_lower = local_path.suffix.lower()

            # Load shape
            if ext_lower in {".step", ".stp"}:
                reader = STEPControl_Reader()
            else:
                reader = IGESControl_Reader()

            status = reader.ReadFile(str(local_path))
            if status != IFSelect_RetDone:
                raise RuntimeError(f"Reader failed for glTF conversion: {status}")

            reader.TransferRoots()
            shape = reader.OneShape()

            if shape is None or shape.IsNull():
                raise ValueError("Null shape for glTF conversion")

            # Tessellate
            mesh_algo = BRepMesh_IncrementalMesh(shape, 0.1, False, 0.5, True)
            mesh_algo.Perform()

            # Extract triangulated faces → numpy arrays
            all_vertices = []
            all_faces = []
            vertex_offset = 0

            explorer = TopExp_Explorer(shape, TopAbs_FACE)
            while explorer.More():
                face = TopoDS.Face_s(explorer.Current())
                location = TopLoc_Location()
                triangulation = BRep_Tool.Triangulation_s(face, location)

                if triangulation is not None:
                    nb_nodes = triangulation.NbNodes()
                    nb_tris = triangulation.NbTriangles()

                    # Extract vertices
                    for i in range(1, nb_nodes + 1):
                        node = triangulation.Node(i)
                        transformed = node.Transformed(location.Transformation())
                        all_vertices.append(
                            [transformed.X(), transformed.Y(), transformed.Z()]
                        )

                    # Extract triangle indices (OCC is 1-based)
                    for i in range(1, nb_tris + 1):
                        tri = triangulation.Triangle(i)
                        n1, n2, n3 = tri.Get()
                        all_faces.append([
                            n1 - 1 + vertex_offset,
                            n2 - 1 + vertex_offset,
                            n3 - 1 + vertex_offset,
                        ])

                    vertex_offset += nb_nodes

                explorer.Next()

            if not all_vertices or not all_faces:
                logger.warning(
                    f"[{model_id}] BRep tessellation produced no geometry — "
                    "falling back to placeholder"
                )
                return _build_placeholder_glb()

            vertices = np.array(all_vertices, dtype=np.float64)
            faces = np.array(all_faces, dtype=np.int64)

            mesh = trimesh.Trimesh(vertices=vertices, faces=faces)
            scene = trimesh.Scene(mesh)
            return scene.export(file_type="glb")

        except ImportError:
            logger.warning(
                f"[{model_id}] OCP not installed — generating placeholder glTF"
            )
            return _build_placeholder_glb()

    return await asyncio.to_thread(_do_convert)


def _build_placeholder_glb() -> bytes:
    """Build a minimal placeholder GLB (unit cube) as fallback."""
    box = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    scene = trimesh.Scene(box)
    return scene.export(file_type="glb")
