"""Quick DB connectivity check."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


async def check():
    url = "postgresql+asyncpg://postgres:postgres@localhost:5432/mechai"
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            print("OK: PostgreSQL connected")
            result = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            )
            rows = result.fetchall()
            if rows:
                print(f"Existing tables ({len(rows)}):")
                for r in rows:
                    print(f"  - {r[0]}")
            else:
                print("No tables yet")
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(check())
