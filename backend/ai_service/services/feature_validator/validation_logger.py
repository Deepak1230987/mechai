"""
Validation Logger — non-blocking logging of feature validation calls.

Persists every (raw_features → validated_features) pair alongside geometry
metadata to the feature_validation_logs table.  This data becomes training
input for future ML validators (Vertex AI).

Logging is fire-and-forget: failures are logged but never propagate to
the planning pipeline.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from ai_service.models import FeatureValidationLog

logger = logging.getLogger(__name__)


class ValidationLogger:
    """
    Logs feature validation calls to PostgreSQL.

    Usage:
        vl = ValidationLogger(session)
        await vl.log(model_id, raw_features, validated_features, geometry_snapshot)
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        model_id: str,
        raw_features: list[dict],
        validated_features: list[dict],
        geometry_snapshot: dict,
    ) -> None:
        """
        Persist a validation record.  Non-blocking — exceptions are caught.

        Args:
            model_id:            FK to models.id
            raw_features:        Features as received from DB
            validated_features:  Features after validation pass
            geometry_snapshot:   Geometry metadata at validation time
        """
        try:
            record = FeatureValidationLog(
                id=str(uuid.uuid4()),
                model_id=model_id,
                raw_features=raw_features,
                validated_features=validated_features,
                geometry_snapshot=geometry_snapshot,
            )
            self._session.add(record)
            # Flush (not commit) so the record is written in the same
            # transaction as the machining plan.  Commit is handled by
            # the FastAPI get_session dependency.
            await self._session.flush()
            logger.debug("Validation log saved for model=%s", model_id)
        except Exception:
            logger.exception("Failed to save validation log for model=%s", model_id)
            # Swallow — logging must never break the planning pipeline.
