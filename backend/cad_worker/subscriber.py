"""
Pub/Sub subscriber for CAD Worker.

Production: subscribes to GCP Pub/Sub topic.
Development: polls the database for PROCESSING models (simple fallback).
"""

import asyncio
import json
import logging

from sqlalchemy import select

from shared.config import get_settings
from shared.db import async_session_factory
from cad_service.models import CADModel
from cad_worker.processor import process_model

logger = logging.getLogger("cad_worker.subscriber")
settings = get_settings()


async def start_subscriber() -> None:
    """Start the appropriate subscriber based on environment."""
    if settings.ENV == "production":
        await _start_pubsub_subscriber()
    else:
        await _start_db_poller()


async def _start_pubsub_subscriber() -> None:
    """
    Production Pub/Sub subscriber.
    Placeholder — will use google.cloud.pubsub_v1.SubscriberClient.
    """
    # from google.cloud import pubsub_v1
    # subscriber = pubsub_v1.SubscriberClient()
    # subscription_path = subscriber.subscription_path(
    #     settings.GCP_PROJECT_ID, settings.PUBSUB_SUBSCRIPTION
    # )
    #
    # def callback(message):
    #     data = json.loads(message.data.decode("utf-8"))
    #     asyncio.run(process_model(data["model_id"], data["gcs_path"]))
    #     message.ack()
    #
    # streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    # streaming_pull_future.result()
    raise NotImplementedError("Production Pub/Sub subscriber not configured yet")


async def _start_db_poller() -> None:
    """
    Development fallback: poll the database for models with PROCESSING status.
    Simple approach for local development without GCP Pub/Sub.
    """
    logger.info("Starting DB poller (development mode)...")
    processed_ids: set[str] = set()

    while True:
        try:
            async with async_session_factory() as session:
                result = await session.execute(
                    select(CADModel).where(CADModel.status == "PROCESSING")
                )
                models = result.scalars().all()

                for model in models:
                    if model.id not in processed_ids:
                        processed_ids.add(model.id)
                        logger.info(f"Found PROCESSING model: {model.id}")
                        # Process in background so we don't block polling
                        asyncio.create_task(
                            _safe_process(model.id, model.gcs_path or "")
                        )

        except Exception as e:
            logger.error(f"DB poller error: {e}")

        await asyncio.sleep(5)  # Poll every 5 seconds


async def _safe_process(model_id: str, gcs_path: str) -> None:
    """Wrapper to catch and log processing errors."""
    try:
        await process_model(model_id, gcs_path)
    except Exception as e:
        logger.error(f"Processing failed for {model_id}: {e}")
