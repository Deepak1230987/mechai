import requests
import json

# Get a model that has plans
r = requests.get('http://localhost:8003/planning/0af7d876-d89b-4d0f-9d66-38b11c8626db/latest')
print('Latest status:', r.status_code)
if r.status_code == 200:
    d = r.json()
    model_id = d['model_id']
    version = d['version']
    print(f'  model_id: {model_id}, version: {version}')

    # Test list versions
    r2 = requests.get(f'http://localhost:8003/planning/{model_id}/versions')
    print('Versions status:', r2.status_code)
    if r2.status_code == 200:
        versions = r2.json()
        print(f'  Found {len(versions)} version(s)')
        for v in versions:
            print(f'    v{v["version"]} - approved={v["approved"]} ops={v["operation_count"]} time={v["estimated_time"]}s created={v["created_at"][:19]}')

        # Test get specific version (oldest)
        first_version = versions[-1]['version']
        r3 = requests.get(f'http://localhost:8003/planning/{model_id}/version/{first_version}')
        print(f'Get v{first_version} status:', r3.status_code)
        if r3.status_code == 200:
            vd = r3.json()
            print(f'  plan_id={vd["plan_id"]}, version={vd["version"]}, ops={len(vd["operations"])}')
    else:
        print('  Error:', r2.text[:200])
else:
    print('  Error:', r.text[:200])
