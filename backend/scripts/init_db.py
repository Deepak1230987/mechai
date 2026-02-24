"""
Database initialization script.
Creates all tables without Alembic (useful for quick dev setup).

Usage:
  cd backend
  python -m scripts.init_db
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.db import engine, Base

# Import models to register them with Base.metadata
from auth_service.models import User          # noqa: F401
from cad_service.models import CADModel       # noqa: F401


async def init_db():
    print("Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Done! Tables created:")
    for table_name in Base.metadata.tables:
        print(f"  ✓ {table_name}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
