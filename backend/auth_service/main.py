"""
Auth Service — standalone FastAPI application.

Responsibilities:
  • Register new users
  • Authenticate (login) and issue JWT
  • Role management

Database scope: users table ONLY.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.config import get_settings
from auth_service.routes import auth_router

settings = get_settings()

app = FastAPI(
    title="Auth Service",
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

app.include_router(auth_router, prefix="/auth", tags=["Auth"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth_service"}
