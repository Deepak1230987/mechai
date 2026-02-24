"""
API Gateway — single entry point for all frontend requests.

Responsibilities:
  • Route requests to the correct internal service
  • Verify JWT and attach user context (X-User-ID, X-User-Role headers)
  • Central request logging
  • CORS handling

Does NOT implement any business logic.

Routing:
  /api/v1/auth/*   → Auth Service   (localhost:8001)
  /api/v1/models/* → CAD Service    (localhost:8002)

Future:
  /api/v1/ai/*        → AI Service
  /api/v1/rfq/*       → RFQ Service
  /api/v1/community/* → Community Service
"""

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import get_settings
from api_gateway.routes import gateway_router
from api_gateway.middleware import RequestLoggingMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

settings = get_settings()

app = FastAPI(
    title="AI-CAM-RFQ API Gateway",
    version="0.1.0",
    docs_url="/docs",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Logging middleware ────────────────────────────────────────────────────────
app.add_middleware(RequestLoggingMiddleware)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(gateway_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api_gateway"}
