"""
Storage service for CAD Worker.

Wraps the shared storage module to provide worker-specific helpers:
  • Download CAD files to a local temp path for engine processing
  • Provide absolute local paths for geometry engines

No authentication logic. No API routes.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from shared.config import get_settings
from shared.storage import read_file, local_abs_path, file_exists

logger = logging.getLogger("cad_worker.storage_service")
settings = get_settings()

# Maximum file size the worker will process (100 MB)
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024


async def download_file(storage_path: str) -> Path:
    """
    Download a CAD file from storage to a local temporary path.

    In dev mode, the file already exists on disk — we just return the
    absolute path. In production, we download from GCS to a temp file.

    Args:
        storage_path: Logical path (e.g. "uploads/<user>/<model>/part.step")

    Returns:
        Absolute Path to the local file on disk.

    Raises:
        FileNotFoundError: If the file does not exist in storage.
        ValueError: If the file exceeds MAX_FILE_SIZE_BYTES.
    """
    if not file_exists(storage_path):
        raise FileNotFoundError(f"CAD file not found in storage: {storage_path}")

    if settings.ENV != "production":
        # Dev mode — file is already on local disk
        local_path = local_abs_path(storage_path)
        _validate_file_size(local_path)
        logger.info(f"Using local file: {local_path}")
        return local_path

    # Production — download from GCS to a temp file
    data = await read_file(storage_path)
    if len(data) > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File exceeds max size: {len(data)} bytes > {MAX_FILE_SIZE_BYTES} bytes"
        )

    # Preserve the original extension for the geometry engine
    suffix = Path(storage_path).suffix
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(data)
    tmp.close()

    logger.info(f"Downloaded to temp file: {tmp.name} ({len(data)} bytes)")
    return Path(tmp.name)


def get_local_file_path(storage_path: str) -> Path:
    """
    Get the absolute local path for a file (dev mode only helper).
    """
    return local_abs_path(storage_path)


def _validate_file_size(path: Path) -> None:
    """Raise ValueError if the file exceeds the max allowed size."""
    size = path.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"File exceeds max size: {size} bytes > {MAX_FILE_SIZE_BYTES} bytes"
        )
