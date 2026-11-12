"""End-to-end test: prep/membrane embedding flow."""
import http.client
import json
import time

TOKEN = "dw_EWdPlif6iJZu70abMVa9i8ZoI1jy9Z3_4f05jORX_n1T1jJHV40vmsA3dLcPT"
WORKER_TOKEN = "ciJ0l7AshBqWge6NSQ4ytprdc76nvndiROHU8iswcDUfW-sVaVhw4XhZRSNpuXR3"


def api_request(method, path, body=None, content_type="application/json", files=None, token=TOKEN):
    conn = http.client.HTTPConnection("127.0.0.1", 8000)
    headers = {"Authorization": f"Bearer {token}"}

    if files:
        boundary = "----PrepTestBoundary12345"
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


print("=== Step 1: Upload protein for membrane embedding ===")
status, result = upload_file("/data/protein.pdb", "protein.pdb", "chemical/x-pdb")
print(f"Status: {status}")
if status != 201:
    print(f"FAILED: {result}")
    raise SystemExit(1)
protein_file_id = result["id"]
print(f"Protein file ID: {protein_file_id}")

print("\n=== Step 2: Request membrane embedding ===")
payload = {
    "protein_file_id": protein_file_id,
    "lipid": "POPC",
    "box_padding_nm": 1.5,
    "orientation": None,
    "ionic_strength_molar": 0.15,
}
status, result = api_request("POST", "/api/v1/prep/membrane", body=payload)
print(f"Status: {status}")
if status != 200:
    print(f"FAILED: {result}")
    raise SystemExit(1)
prep_job_id = result["prep_job_id"]
print(f"Prep job ID: {prep_job_id}")
print(f"Status: {result['status']}")

print("\n=== Step 3: Poll prep job status ===")
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

print("\nPrep job completed!")

print("\n=== Step 4: List prep jobs ===")
status, result = api_request("GET", "/api/v1/prep/jobs")
for job in result:
    print(f"  {job['id']}: {job['type']} {job['status']} output_files={job.get('output_file_ids', [])}")

print("\n=== PREP E2E TEST PASSED ===")
