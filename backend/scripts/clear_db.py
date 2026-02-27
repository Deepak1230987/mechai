"""
Clear all data from all tables in the mechai database.
Keeps table structure intact - only deletes rows.

Usage:
  cd backend
  python -m scripts.clear_db
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from shared.db import engine


async def clear_all_tables():
    async with engine.begin() as conn:
        # Get all table names
        result = await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        tables = [row[0] for row in result.fetchall()]

        if not tables:
            print("No tables found.")
            return

        print(f"Found {len(tables)} tables: {', '.join(tables)}")

        # Truncate all tables with CASCADE to handle FK constraints
        table_list = ", ".join(f'"{t}"' for t in tables)
        await conn.execute(text(f"TRUNCATE {table_list} CASCADE"))

        print(f"All data cleared from {len(tables)} tables.")


if __name__ == "__main__":
    asyncio.run(clear_all_tables())
