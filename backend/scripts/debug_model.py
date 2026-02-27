"""Quick diagnostic: check model, geometry, features for a given model_id."""
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from shared.db.session import engine as async_engine

MODEL_ID = "0af7d876-d89b-4d0f-9d66-38b11c8626db"

async def main():
    async with async_engine.connect() as conn:
        # List all tables
        r = await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        ))
        rows = r.fetchall()
        print("Tables:", [r[0] for r in rows])

        # Check model_geometry columns
        r = await conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'model_geometry' ORDER BY ordinal_position"
        ))
        rows = r.fetchall()
        print("\nmodel_geometry columns:")
        for row in rows:
            print(f"  {row[0]}: {row[1]}")

        # Check model
        r = await conn.execute(text(
            f"SELECT id, name, file_format, status FROM models WHERE id = '{MODEL_ID}'"
        ))
        row = r.fetchone()
        print(f"\nModel: {row}")

        # Check geometry (only columns that exist)
        r = await conn.execute(text(
            f"SELECT model_id, volume, surface_area, feature_ready, planar_faces, cylindrical_faces FROM model_geometry WHERE model_id = '{MODEL_ID}'"
        ))
        row = r.fetchone()
        print(f"Geometry: {row}")

        # Check features
        r = await conn.execute(text(
            f"SELECT id, type, confidence, depth, diameter FROM model_features WHERE model_id = '{MODEL_ID}'"
        ))
        rows = r.fetchall()
        print(f"Features ({len(rows)}):")
        for fr in rows:
            print("  ", fr)

asyncio.run(main())
