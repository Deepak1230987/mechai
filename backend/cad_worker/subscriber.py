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
from cad_worker.worker import process_message

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
    Subscribes to the GCP Pub/Sub topic and processes messages.
    """
    from google.cloud import pubsub_v1
    from concurrent.futures import TimeoutError as FuturesTimeout

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(
        settings.GCP_PROJECT_ID, settings.PUBSUB_SUBSCRIPTION
    )

    logger.info(f"Subscribing to {subscription_path}...")

    def callback(message: pubsub_v1.subscriber.message.Message) -> None:
        try:
            data = json.loads(message.data.decode("utf-8"))
            model_id = data.get("model_id", "")
            gcs_path = data.get("gcs_path", "")
            logger.info(f"Received Pub/Sub message for model {model_id}")

            # Run the async processor in a new event loop
            # (callback runs in a thread managed by the subscriber)
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(process_message(model_id, gcs_path))
            finally:
                loop.close()

            message.ack()
            logger.info(f"Message acknowledged for model {model_id}")
        except Exception as e:
            logger.error(f"Error processing Pub/Sub message: {e}")
            message.nack()

    streaming_pull_future = subscriber.subscribe(subscription_path, callback=callback)
    logger.info("Pub/Sub subscriber started — listening for messages...")

    # Block indefinitely, handling messages via the callback
    try:
        streaming_pull_future.result()
    except FuturesTimeout:
        streaming_pull_future.cancel()
        streaming_pull_future.result()
    except KeyboardInterrupt:
        streaming_pull_future.cancel()
        logger.info("Pub/Sub subscriber stopped.")


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
        await process_message(model_id, gcs_path)
    except Exception as e:
        logger.error(f"Processing failed for {model_id}: {e}")
