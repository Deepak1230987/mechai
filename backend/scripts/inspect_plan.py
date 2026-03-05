"""Quick script to inspect the stored plan data."""
import asyncio
import json
from shared.db import get_session
from sqlalchemy import text

async def main():
    async for session in get_session():
        r = await session.execute(text(
            "SELECT plan_data FROM machining_plans "
            "WHERE model_id='f6f058c1-08f9-4a94-a81a-dd3ed40ef89a' "
            "ORDER BY version DESC LIMIT 1"
        ))
        row = r.fetchone()
        if row:
            pd = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            print("=== operations ===")
            for op in pd.get("operations", []):
                print(f"  {op['id']}: {op['type']} feature={op['feature_id']}")
                print(f"    params={json.dumps(op.get('parameters',{}))}")
            print("\n=== setups ===")
            for s in pd.get("setups", []):
                print(f"  {s['setup_id']}: orient={s['orientation']} ops={s['operations']}")
            print("\n=== strategies ===")
            for st in pd.get("strategies", []):
                print(f"  {st['name']}: time={st['estimated_time']}")
            print("\n=== risks ===")
            for r2 in pd.get("risks", []):
                print(f"  {r2}")
            print("\n=== tools ===")
            for t in pd.get("tools", []):
                print(f"  {t['id']}: {t['type']} d={t['diameter']}")
            print(f"\n=== generation_explanation ===")
            print(f"  {pd.get('generation_explanation', 'NONE')}")
            print(f"\n=== selected_strategy ===")
            print(f"  {pd.get('selected_strategy', 'NONE')}")
        break

asyncio.run(main())
