"""
Development-only file endpoints.

These routes handle the "signed URL" uploads and file serving
when running locally without GCS.

Upload:  PUT  /dev/upload/{path:path}   — receives raw bytes from the frontend
Serve:   GET  /dev/files/{path:path}    — serves stored files back (glTF, etc.)

In production these routes are never mounted; real GCS signed
URLs are used instead.
"""

import logging

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse, Response

from shared.storage import save_file, file_exists, local_abs_path

logger = logging.getLogger(__name__)

dev_files_router = APIRouter(tags=["Dev Files"])


@dev_files_router.put("/dev/upload/{file_path:path}")
async def dev_upload(file_path: str, request: Request) -> dict:
    """
    Accept a raw binary PUT (same as a GCS signed-URL upload).
    The frontend sends the file body directly here.
    """
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")

    await save_file(file_path, body)
    logger.info(f"[DEV] Received upload: {file_path} ({len(body)} bytes)")
    return {"status": "ok", "path": file_path, "size": len(body)}


@dev_files_router.get("/dev/files/{file_path:path}")
async def dev_serve(file_path: str):
    """
    Serve a file from local storage — used as the dev equivalent of a
    GCS signed read URL.
    """
    if not file_exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    abs_path = local_abs_path(file_path)

    # Determine content type from extension
    suffix = abs_path.suffix.lower()
    content_types = {
        ".gltf": "model/gltf+json",
        ".glb": "model/gltf-binary",
        ".bin": "application/octet-stream",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".step": "application/octet-stream",
        ".stp": "application/octet-stream",
        ".iges": "application/octet-stream",
        ".igs": "application/octet-stream",
        ".stl": "application/octet-stream",
        ".x_t": "application/octet-stream",
    }
    media_type = content_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(abs_path),
        media_type=media_type,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache",
        },
    )
