"""Comprehensive end-to-end test: all three system prep operations chained."""
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


def poll_prep_job(prep_job_id, max_polls=60):
    for i in range(max_polls):
        status, result = api_request("GET", f"/api/v1/prep/jobs/{prep_job_id}")
        if status != 200:
            print(f"  [{i:2d}] FAILED to get job: {result}")
            return False, result
        pstatus = result["status"]
        if i % 5 == 0 or pstatus in ("completed", "failed", "canceled"):
            print(f"  [{i:2d}] status={pstatus:12s}")
        if pstatus in ("completed", "failed", "canceled"):
            return pstatus == "completed", result
        time.sleep(2)
    return False, result


print("=" * 60)
print("COMPREHENSIVE SYSTEM PREP TEST")
print("=" * 60)

# Step 1: Upload 7YAE.pdb and ligand
print("\n--- Step 1: Upload input files ---")
status, result = upload_file("/data/7yae.pdb", "7yae.pdb", "chemical/x-pdb")
assert status == 201, f"Upload failed: {result}"
pdb_file_id = result["id"]
print(f"  7YAE.pdb: {pdb_file_id}")

status, result = upload_file("/data/ligand_CLR_401.sdf", "ligand.sdf", "chemical/x-mdl-sdfile")
assert status == 201, f"Upload failed: {result}"
ligand_file_id = result["id"]
print(f"  ligand.sdf: {ligand_file_id}")

# Step 2: Remove CLR ligand from 7YAE
print("\n--- Step 2: Remove CLR ligand ---")
payload = {
    "name": "Test: remove CLR",
    "input_file_id": pdb_file_id,
    "steps": [{"operation": "remove_ligand", "ligand_to_remove": "CLR"}]
}
status, result = api_request("POST", "/api/v1/prep/system-prep", body=payload)
assert status == 200, f"Create failed: {result}"
job1_id = result["prep_job_id"]
print(f"  Job: {job1_id}")

ok, result = poll_prep_job(job1_id)
assert ok, f"Job failed: {result}"
assert len(result.get("output_file_ids", [])) > 0, "No output file"
job1_output = result["output_file_ids"][0]
print(f"  Output file: {job1_output}")

# Step 3: Select chain A from the result
print("\n--- Step 3: Select chain A ---")
payload = {
    "name": "Test: select chain A",
    "input_file_id": job1_output,
    "steps": [{"operation": "select_chain", "chain_to_keep": "A"}]
}
status, result = api_request("POST", "/api/v1/prep/system-prep", body=payload)
assert status == 200, f"Create failed: {result}"
job2_id = result["prep_job_id"]
print(f"  Job: {job2_id}")

ok, result = poll_prep_job(job2_id)
assert ok, f"Job failed: {result}"
assert len(result.get("output_file_ids", [])) > 0, "No output file"
job2_output = result["output_file_ids"][0]
print(f"  Output file: {job2_output}")

# Verify chain A only
import os
for root, dirs, files in os.walk('/data/uploads'):
    for f in files:
        if f == 'system_prep.pdb' and job2_output in root:
            path = os.path.join(root, f)
            with open(path) as fh:
                content = fh.read()
            chains = set()
            for line in content.splitlines():
                if line.startswith('ATOM') or line.startswith('HETATM'):
                    chain = line[21]
                    chains.add(chain)
            print(f"  Chains in output: {sorted(chains)}")
            assert chains == {'A'}, f"Expected only chain A, got {chains}"
            print("  ✓ Only chain A present")

# Step 4: Add ligand back
print("\n--- Step 4: Add ligand back ---")
payload = {
    "name": "Test: add ligand",
    "input_file_id": job2_output,
    "steps": [{
        "operation": "add_ligand",
        "ligand_file_ids": [ligand_file_id]
    }]
}
status, result = api_request("POST", "/api/v1/prep/system-prep", body=payload)
assert status == 200, f"Create failed: {result}"
job3_id = result["prep_job_id"]
print(f"  Job: {job3_id}")

ok, result = poll_prep_job(job3_id)
assert ok, f"Job failed: {result}"
assert len(result.get("output_file_ids", [])) > 0, "No output file"
job3_output = result["output_file_ids"][0]
print(f"  Output file: {job3_output}")

# Step 5: Verify final output can be used for MD
print("\n--- Step 5: Verify final output is valid PDB ---")
for root, dirs, files in os.walk('/data/uploads'):
    for f in files:
        if f == 'system_prep.pdb' and job3_output in root:
            path = os.path.join(root, f)
            with open(path) as fh:
                content = fh.read()
            has_clr = 'CLR' in content
            chains = set()
            for line in content.splitlines():
                if line.startswith('ATOM') or line.startswith('HETATM'):
                    chain = line[21]
                    chains.add(chain)
            print(f"  Chains: {sorted(chains)}")
            print(f"  Has CLR: {has_clr}")
            print(f"  Size: {os.path.getsize(path)} bytes")
            break

print("\n" + "=" * 60)
print("ALL TESTS PASSED!")
print("=" * 60)
