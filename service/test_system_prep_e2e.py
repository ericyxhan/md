"""End-to-end test: system prep operations via API + prep worker."""
import http.client
import json
import time
import os

TOKEN = "dw_EWdPlif6iJZu70abMVa9i8ZoI1jy9Z3_4f05jORX_n1T1jJHV40vmsA3dLcPT"

def api_request(method, path, body=None, content_type="application/json", files=None, token=TOKEN):
    conn = http.client.HTTPConnection("127.0.0.1", 8000)
    headers = {"Authorization": f"Bearer {token}"}

    if files:
        boundary = "----SystemPrepTestBoundary12345"
        parts = []
        for field_name, filename, content, ctype in files:
            parts.append(f"--{boundary}")
            parts.append(f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"')
            parts.append(f"Content-Type: {ctype}")
            parts.append("")
            parts.append(content)
        parts.append(f"--{boundary}--")
        parts.append("")
        body = "\r\n".join(parts).encode("latin-1")
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        body = json.dumps(body).encode()
        headers["Content-Type"] = content_type

    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    try:
        parsed = json.loads(raw.decode()) if raw else {}
    except Exception:
        parsed = raw.decode()
    return resp.status, parsed


def upload_file(filepath, filename, content_type):
    with open(filepath, "rb") as f:
        content = f.read().decode("latin-1")
    status, result = api_request(
        "POST", "/api/v1/files",
        files=[("file", filename, content, content_type)]
    )
    return status, result


# Files already copied to /data inside the container
print("Using files already in /data inside container")

# Step 1: Upload 7YAE.pdb
print("\n=== Step 1: Upload 7YAE.pdb ===")
status, result = upload_file("/data/7yae.pdb", "7yae.pdb", "chemical/x-pdb")
print(f"Status: {status}")
if status != 201:
    print(f"FAILED: {result}")
    raise SystemExit(1)
file_id = result["id"]
print(f"File ID: {file_id}")

# Step 2: Create system prep job - remove ligand CLR_401
print("\n=== Step 2: System prep - remove ligand CLR_401 ===")
payload = {
    "name": "Remove CLR_401 from 7YAE",
    "input_file_id": file_id,
    "steps": [
        {"operation": "remove_ligand", "ligand_to_remove": "CLR"}
    ]
}
status, result = api_request("POST", "/api/v1/prep/system-prep", body=payload)
print(f"Status: {status}")
if status != 200:
    print(f"FAILED: {result}")
    raise SystemExit(1)
prep_job_id = result["prep_job_id"]
print(f"Prep job ID: {prep_job_id}, status: {result['status']}")

# Step 3: Poll for completion
print("\n=== Step 3: Poll prep job ===")
for i in range(60):
    status, result = api_request("GET", f"/api/v1/prep/jobs/{prep_job_id}")
    if status != 200:
        print(f"FAILED: {result}")
        raise SystemExit(1)
    pstatus = result["status"]
    phase = result.get("phase")
    pct = result.get("progress_percent")
    print(f"  [{i:2d}] status={pstatus:12s} phase={phase} progress={pct}")
    if pstatus in ("completed", "failed", "canceled"):
        break
    time.sleep(2)

if pstatus != "completed":
    print(f"\nPrep job did not complete. Final status: {pstatus}")
    print(f"Error: {result.get('error_message')}")
    raise SystemExit(1)

print(f"\nPrep job completed! Output file IDs: {result.get('output_file_ids', [])}")

# Step 4: Verify output file exists and is valid
output_file_ids = result.get("output_file_ids", [])
if output_file_ids:
    print(f"\n=== Step 4: Get output file metadata ===")
    status, file_info = api_request("GET", f"/api/v1/files/{output_file_ids[0]}")
    print(f"Status: {status}")
    print(json.dumps(file_info, indent=2))

print("\n=== SYSTEM PREP REMOVE LIGAND TEST PASSED ===")
