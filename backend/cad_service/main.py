"""
CAD Service — standalone FastAPI application.

Responsibilities:
  • Generate signed upload URLs (GCS)
  • Store model metadata
  • Track model processing status
  • Confirm upload & publish Pub/Sub event
  • Generate signed glTF read URLs

Database scope: models table ONLY.
Does NOT do: authentication, feature recognition, AI planning.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import get_settings
from cad_service.routes import models_router, dev_files_router

settings = get_settings()

app = FastAPI(
    title="CAD Service",
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

app.include_router(models_router, prefix="/models", tags=["Models"])

# Dev-only endpoints for local file upload & serving (replaces GCS signed URLs)
if settings.ENV != "production":
    app.include_router(dev_files_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "cad_service"}
