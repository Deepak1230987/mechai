"""
File storage abstraction layer.

Development:  stores files on local disk under LOCAL_STORAGE_PATH.
Production:   stores files in Google Cloud Storage (GCS).

Every path argument is a *logical path* like "uploads/<user>/<model>/file.step"
— the same string stored in CADModel.gcs_path / gltf_path.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _local_root() -> Path:
    """Resolve the local storage root, relative to the backend directory."""
    root = Path(settings.LOCAL_STORAGE_PATH)
    if not root.is_absolute():
        # Resolve relative to the backend/ directory (parent of shared/)
        root = Path(__file__).resolve().parent.parent / root
    root.mkdir(parents=True, exist_ok=True)
    return root


# ── Public API ────────────────────────────────────────────────────────────────

async def save_file(logical_path: str, data: bytes) -> None:
    """
    Persist raw bytes to storage.

    Args:
        logical_path: e.g. "uploads/<user_id>/<model_id>/part.step"
        data:         raw file bytes
    """
    if settings.ENV == "production":
        await _gcs_upload(logical_path, data)
    else:
        _local_save(logical_path, data)


async def read_file(logical_path: str) -> bytes:
    """
    Read raw bytes from storage.

    Returns:
        File contents as bytes.

    Raises:
        FileNotFoundError: if the file does not exist.
    """
    if settings.ENV == "production":
        return await _gcs_download(logical_path)
    return _local_read(logical_path)


def file_exists(logical_path: str) -> bool:
    """Check whether a file exists in storage."""
    if settings.ENV == "production":
        return _gcs_exists(logical_path)
    return _local_exists(logical_path)


def local_abs_path(logical_path: str) -> Path:
    """
    Return the absolute filesystem path for a logical path.
    Only valid in dev mode.
    """
    return _local_root() / logical_path


# ── Local (dev) implementation ────────────────────────────────────────────────

def _local_save(logical_path: str, data: bytes) -> None:
    dest = _local_root() / logical_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    logger.info(f"[LOCAL] Saved {len(data)} bytes → {dest}")


def _local_read(logical_path: str) -> bytes:
    src = _local_root() / logical_path
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")
    return src.read_bytes()


def _local_exists(logical_path: str) -> bool:
    return (_local_root() / logical_path).exists()


# ── GCS (production) implementation ──────────────────────────────────────────

async def _gcs_upload(logical_path: str, data: bytes) -> None:
    from google.cloud import storage as gcs

    client = gcs.Client(project=settings.GCP_PROJECT_ID)
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(logical_path)
    blob.upload_from_string(data, content_type="application/octet-stream")
    logger.info(f"[GCS] Uploaded {len(data)} bytes → gs://{settings.GCS_BUCKET_NAME}/{logical_path}")


async def _gcs_download(logical_path: str) -> bytes:
    from google.cloud import storage as gcs

    client = gcs.Client(project=settings.GCP_PROJECT_ID)
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(logical_path)
    if not blob.exists():
        raise FileNotFoundError(f"GCS blob not found: {logical_path}")
    return blob.download_as_bytes()


def _gcs_exists(logical_path: str) -> bool:
    from google.cloud import storage as gcs

    client = gcs.Client(project=settings.GCP_PROJECT_ID)
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    return bucket.blob(logical_path).exists()
