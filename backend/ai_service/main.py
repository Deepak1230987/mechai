"""
AI Service — standalone FastAPI application.

Responsibilities:
    • Deterministic machining plan generation (rule engine)
    • Tool selection from catalogue
    • Time estimation

Future:
    • LLM-based plan optimisation (sits on top of rule engine)
    • Human-in-loop plan editing + re-validation
    • Cost estimation

Does NOT contain:
    • Authentication (handled by gateway / auth service)
    • Geometry processing (CAD Worker)
    • File storage (CAD Service)
"""

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import get_settings
from ai_service.routes.planning import planning_router
from ai_service.routes.intelligence import intelligence_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

settings = get_settings()

app = FastAPI(
    title="AI Service (Rule Engine)",
    version="0.1.0",
    docs_url="/docs",
    root_path="",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(planning_router)
app.include_router(intelligence_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ai_service"}
