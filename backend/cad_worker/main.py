"""
CAD Worker — Pure Background Process (No HTTP Routes).

Responsibilities:
  • Subscribe to Pub/Sub (or poll DB in dev mode)
  • Download CAD file from GCS
  • Process with OpenCascade (placeholder)
  • Generate glTF output
  • Upload glTF to GCS
  • Update model status to READY (or FAILED)

This is NOT a FastAPI app. It runs as a standalone async process.
"""

import asyncio
import json
import logging
import sys

from cad_worker.processor import process_model
from cad_worker.subscriber import start_subscriber

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("cad_worker")


async def main():
    logger.info("CAD Worker starting...")
    await start_subscriber()


if __name__ == "__main__":
    asyncio.run(main())
