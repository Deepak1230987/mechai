"""
Database initialization script.
Creates all tables from current SQLAlchemy models (no Alembic).

Supports two modes:
  --reset   Drop ALL tables first, then recreate (destructive!)
  (default) Create tables if not existing (safe, idempotent)

Usage:
  cd backend
  python -m scripts.init_db          # safe create
  python -m scripts.init_db --reset  # drop + recreate
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import engine, Base

# ── Import ALL models to register them with Base.metadata ─────────────────────
# Auth Service
from auth_service.models import User                    # noqa: F401

# CAD Service
from cad_service.models import CADModel                 # noqa: F401

# CAD Worker
from cad_worker.models import ModelGeometry             # noqa: F401
from cad_worker.models import ModelFeature              # noqa: F401

# AI Service (Phase B — hybrid co-planner)
from ai_service.models import MachiningPlan             # noqa: F401
from ai_service.models import FeatureValidationLog      # noqa: F401
from ai_service.models import PlanFeedback              # noqa: F401


async def init_db(reset: bool = False):
    async with engine.begin() as conn:
        if reset:
            print("⚠  Dropping ALL tables (--reset)...")
            await conn.run_sync(Base.metadata.drop_all)
            print("   All tables dropped.")

        print("Creating database tables...")
        await conn.run_sync(Base.metadata.create_all)

    print(f"\nDone! {len(Base.metadata.tables)} tables ready:")
    for table_name in sorted(Base.metadata.tables):
        print(f"  ✓ {table_name}")

    await engine.dispose()


if __name__ == "__main__":
    do_reset = "--reset" in sys.argv
    asyncio.run(init_db(reset=do_reset))
