import asyncio
import httpx
import sys
import os

sys.path.insert(0, r"F:\StartUp\Project1\mechai\backend")

async def test_chat():
    from sqlalchemy import select
    from shared.db import async_session_factory
    from ai_service.models import MachiningPlan
    
    async with async_session_factory() as session:
        result = await session.execute(select(MachiningPlan.id).limit(1))
        plan_id = result.scalar_one_or_none()
        
    if not plan_id:
        print("No machining plans found in DB. Need a model to be approved first.")
        return
        
    print(f"Using plan_id: {plan_id}")
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        print("\n--- Testing GENERAL_CONVERSATION ---")
        try:
            res1 = await client.post(
                f"http://localhost:8003/planning/{plan_id}/chat",
                json={"user_message": "Hi there! What is the material of this part?"}
            )
            print(f"Status: {res1.status_code}")
            import json
            print(f"Response: {json.dumps(res1.json(), indent=2)}")
        except Exception as e:
            print(f"Error: {e}")

        print("\n--- Testing PLAN_MODIFICATION ---")
        try:
            res2 = await client.post(
                f"http://localhost:8003/planning/{plan_id}/chat",
                json={"user_message": "Change the tool for the main facing operation to a 10mm flat end mill."}
            )
            print(f"Status: {res2.status_code}")
            import json
            res_json = res2.json()
            if "machining_plan" in res_json and isinstance(res_json["machining_plan"], dict):
                res_json["machining_plan"] = "<machining_plan object...>"
            print(f"Response: {json.dumps(res_json, indent=2)}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_chat())
