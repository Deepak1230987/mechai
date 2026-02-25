"""
End-to-end test: Register → Login → Upload STEP → CAD Worker processes → Planning.

Run with:
    cd backend
    python -m scripts.e2e_test
"""

import asyncio
import sys
import os
import uuid
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

GATEWAY = "http://localhost:8000/api/v1"
AUTH_DIRECT = "http://localhost:8001"
CAD_DIRECT = "http://localhost:8002"
AI_DIRECT = "http://localhost:8003"

# Unique test user
TEST_EMAIL = f"e2e_{uuid.uuid4().hex[:8]}@test.com"
TEST_PASSWORD = "TestPass123!"


def step(name: str):
    print(f"\n{'='*60}")
    print(f"  STEP: {name}")
    print(f"{'='*60}")


def main():
    # ── 1. Register ──────────────────────────────────────────────────────────
    step("Register user")
    r = requests.post(f"{GATEWAY}/auth/register", json={
        "name": "E2E Test User",
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    })
    print(f"  Status: {r.status_code}")
    print(f"  Body: {json.dumps(r.json(), indent=2)}")
    assert r.status_code in (200, 201), f"Register failed: {r.text}"
    user_data = r.json().get("user", r.json())
    user_id = user_data.get("id") or user_data.get("user_id")
    print(f"  User ID: {user_id}")

    # ── 2. Login ─────────────────────────────────────────────────────────────
    step("Login")
    r = requests.post(f"{GATEWAY}/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    })
    print(f"  Status: {r.status_code}")
    assert r.status_code == 200, f"Login failed: {r.text}"
    token = r.json().get("access_token")
    print(f"  Token: {token[:30]}...")
    headers = {"Authorization": f"Bearer {token}"}

    # ── 3. Request upload URL ────────────────────────────────────────────────
    step("Request upload URL")
    r = requests.post(f"{GATEWAY}/models/upload", json={
        "filename": "test_part.step",
        "file_format": "STEP",
        "name": "E2E Test Part",
    }, headers=headers)
    print(f"  Status: {r.status_code}")
    print(f"  Body: {json.dumps(r.json(), indent=2)}")
    assert r.status_code in (200, 201), f"Upload request failed: {r.text}"
    model_id = r.json()["model_id"]
    signed_url = r.json()["signed_url"]
    print(f"  Model ID: {model_id}")

    # ── 4. Upload a small STEP file (via dev endpoint) ───────────────────────
    step("Upload STEP file (dev endpoint)")
    # Create a minimal STEP file content
    step_content = b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION((''), '2;1');
FILE_NAME('test_part.step', '2026-02-26', (''), (''), '', '', '');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));
ENDSEC;
DATA;
#1=SHAPE_REPRESENTATION('',(#2),#3);
#2=AXIS2_PLACEMENT_3D('',#4,#5,#6);
#3=(GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNIT_ASSIGNED_CONTEXT((#7,#8,#9)) REPRESENTATION_CONTEXT('',''));
#4=CARTESIAN_POINT('',(0.,0.,0.));
#5=DIRECTION('',(0.,0.,1.));
#6=DIRECTION('',(1.,0.,0.));
#7=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));
#8=(NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.));
#9=(NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT());
ENDSEC;
END-ISO-10303-21;"""

    r = requests.put(
        signed_url,
        data=step_content,
        headers={"Content-Type": "application/octet-stream"},
    )
    print(f"  Upload status: {r.status_code}")
    assert r.status_code in (200, 201, 204), f"File upload failed: {r.text}"

    # ── 5. Confirm upload ────────────────────────────────────────────────────
    step("Confirm upload")
    r = requests.post(f"{GATEWAY}/models/confirm-upload", json={
        "model_id": model_id,
    }, headers=headers)
    print(f"  Status: {r.status_code}")
    print(f"  Body: {json.dumps(r.json(), indent=2)}")
    assert r.status_code in (200, 201), f"Confirm failed: {r.text}"

    # ── 6. Check model status ────────────────────────────────────────────────
    step("Poll model status (waiting for CAD Worker)")
    for i in range(12):
        time.sleep(5)
        r = requests.get(f"{GATEWAY}/models/{model_id}", headers=headers)
        data = r.json()
        status = data.get("status", "UNKNOWN")
        print(f"  [{i+1}/12] Status: {status}")
        if status == "READY":
            print(f"  Model is READY!")
            print(f"  Geometry: {json.dumps(data.get('geometry'), indent=4)}")
            features = data.get("features", [])
            print(f"  Features ({len(features)}):")
            for f in features:
                print(f"    - {f['type']}: {f.get('dimensions', {})}")
            break
        elif status == "FAILED":
            print(f"  Model processing FAILED")
            break
    else:
        print("  Timed out waiting for processing")

    # ── 7. Generate machining plan ───────────────────────────────────────────
    step("Generate machining plan")

    # If model isn't READY or has no features, we'll insert mock features
    # to test the planning pipeline independently
    r = requests.get(f"{GATEWAY}/models/{model_id}", headers=headers)
    model_data = r.json()

    if model_data.get("status") != "READY" or not model_data.get("features"):
        print("  Model not ready or no features — inserting test features directly")
        _insert_test_data(model_id)
        print("  Test data inserted, retrying planning...")

    r = requests.post(f"{AI_DIRECT}/planning/generate", json={
        "model_id": model_id,
        "material": "ALUMINUM_6061",
        "machine_type": "MILLING_3AXIS",
    })
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        plan = r.json()
        print(f"  Plan generated successfully!")
        print(f"  Setups: {len(plan['setups'])}")
        print(f"  Operations: {len(plan['operations'])}")
        for op in plan["operations"]:
            print(f"    - {op['type']} (tool={op['tool_id']}, time={op['estimated_time']}s)")
        print(f"  Tools: {len(plan['tools'])}")
        for t in plan["tools"]:
            print(f"    - {t['id']} ({t['type']}, d={t['diameter']}mm)")
        print(f"  Total estimated time: {plan['estimated_time']}s")
    else:
        print(f"  Planning failed: {r.text}")

    print(f"\n{'='*60}")
    print("  E2E TEST COMPLETE")
    print(f"{'='*60}")


def _insert_test_data(model_id: str):
    """Insert mock geometry + features directly into DB for planning test."""
    import asyncio
    from sqlalchemy import text, update
    from shared.db import async_session_factory
    from cad_service.models import CADModel
    from cad_worker.models import ModelGeometry, ModelFeature

    async def insert():
        async with async_session_factory() as session:
            # Update model status to READY
            await session.execute(
                update(CADModel).where(CADModel.id == model_id).values(status="READY")
            )

            # Insert geometry
            geom = ModelGeometry(
                model_id=model_id,
                geometry_type="BREP",
                bounding_box={"x_min": 0, "y_min": 0, "z_min": 0, "x_max": 100, "y_max": 60, "z_max": 30},
                volume=180000.0,
                surface_area=25200.0,
                planar_faces=6,
                cylindrical_faces=2,
                feature_ready=True,
            )
            session.add(geom)

            # Insert features
            features = [
                ModelFeature(
                    model_id=model_id,
                    type="HOLE",
                    dimensions={"diameter": 8.0, "depth": 25.0},
                    depth=25.0,
                    diameter=8.0,
                    axis={"x": 0, "y": 0, "z": 1},
                    confidence=0.9,
                ),
                ModelFeature(
                    model_id=model_id,
                    type="HOLE",
                    dimensions={"diameter": 5.0, "depth": 15.0},
                    depth=15.0,
                    diameter=5.0,
                    axis={"x": 0, "y": 0, "z": 1},
                    confidence=0.9,
                ),
                ModelFeature(
                    model_id=model_id,
                    type="POCKET",
                    dimensions={"width": 20.0, "length": 40.0, "depth": 10.0},
                    depth=10.0,
                    confidence=0.8,
                ),
                ModelFeature(
                    model_id=model_id,
                    type="SLOT",
                    dimensions={"width": 6.0, "length": 50.0, "depth": 8.0},
                    depth=8.0,
                    confidence=0.75,
                ),
            ]
            for f in features:
                session.add(f)

            await session.commit()
            print(f"  Inserted: 1 geometry + {len(features)} features")

    asyncio.run(insert())


if __name__ == "__main__":
    main()
