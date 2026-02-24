"""Quick end-to-end test for the upload → process → viewer pipeline."""

import requests
import time

BASE = "http://localhost:8000/api/v1"


def main():
    # 1. Register/Login
    print("1. Registering...")
    r = requests.post(
        f"{BASE}/auth/register",
        json={"name": "ViewerTest", "email": "viewer@test.com", "password": "test1234"},
    )
    print(f"   Register response: {r.status_code} {r.text[:200]}")
    if r.status_code in (409, 422):
        print("   User exists or validation error, logging in...")
        r = requests.post(
            f"{BASE}/auth/login",
            json={"email": "viewer@test.com", "password": "test1234"},
        )
        print(f"   Login response: {r.status_code}")
    data = r.json()
    if "access_token" not in data:
        print(f"   ERROR: No access_token in response: {data}")
        return
    token = data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"   Token: {token[:30]}...")

    # 2. Request upload URL
    print("2. Requesting upload URL...")
    r = requests.post(
        f"{BASE}/models/upload",
        json={"filename": "sphere.stl", "file_format": "STL", "name": "Test Sphere"},
        headers=headers,
    )
    upload_data = r.json()
    model_id = upload_data["model_id"]
    signed_url = upload_data["signed_url"]
    print(f"   model_id: {model_id}")
    print(f"   signed_url: {signed_url}")

    # 3. Upload file
    print("3. Uploading STL...")
    import os
    stl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_model.stl")
    with open(stl_path, "rb") as f:
        stl_bytes = f.read()
    r = requests.put(signed_url, data=stl_bytes, headers={"Content-Type": "application/octet-stream"})
    print(f"   Upload status: {r.status_code}")

    # 4. Confirm upload
    print("4. Confirming upload...")
    r = requests.post(
        f"{BASE}/models/confirm-upload",
        json={"model_id": model_id},
        headers=headers,
    )
    print(f"   Status after confirm: {r.json().get('status')}")

    # 5. Poll until READY
    print("5. Waiting for processing...")
    status = None
    for i in range(20):
        time.sleep(2)
        r = requests.get(f"{BASE}/models/{model_id}", headers=headers)
        status = r.json().get("status")
        print(f"   Poll {i+1}: status={status}")
        if status in ("READY", "FAILED"):
            break

    # 6. Get viewer URL
    if status == "READY":
        print("6. Getting viewer URL...")
        r = requests.get(f"{BASE}/models/{model_id}/viewer", headers=headers)
        viewer_data = r.json()
        print(f"   gltf_url: {viewer_data.get('gltf_url')}")
        print("\n=== SUCCESS: Pipeline works end-to-end! ===")
    else:
        print(f"6. SKIPPED — status is {status}")


if __name__ == "__main__":
    main()
