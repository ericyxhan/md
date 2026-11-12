"""End-to-end test: upload -> create job -> worker runs -> complete."""
import http.client
import json
import urllib.error

TOKEN = "dw_EWdPlif6iJZu70abMVa9i8ZoI1jy9Z3_4f05jORX_n1T1jJHV40vmsA3dLcPT"
BASE_HOST = "127.0.0.1"
BASE_PORT = 8000


def api_request(method, path, body=None, content_type="application/json", files=None):
    """Make an HTTP request to the API."""
    conn = http.client.HTTPConnection(BASE_HOST, BASE_PORT)
    headers = {"Authorization": f"Bearer {TOKEN}"}

    if files:
        # Multipart upload
        boundary = "----MDTestBoundary12345"
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


# Step 1: Upload protein
print("=== Step 1: Upload protein.pdb ===")
status, result = upload_file("/data/protein.pdb", "protein.pdb", "chemical/x-pdb")
print(f"Status: {status}")
if status != 201:
    print(f"FAILED: {result}")
    raise SystemExit(1)
protein_file_id = result["id"]
print(f"Protein file ID: {protein_file_id}")

# Step 2: Upload ligand
print("\n=== Step 2: Upload ligand_CLR_401.sdf ===")
status, result = upload_file("/data/ligand_CLR_401.sdf", "ligand.sdf", "chemical/x-mdl-sdfile")
print(f"Status: {status}")
if status != 201:
    print(f"FAILED: {result}")
    raise SystemExit(1)
ligand_file_id = result["id"]
print(f"Ligand file ID: {ligand_file_id}")

# Step 3: Validate job creation
print("\n=== Step 3: Validate job ===")
payload = {
    "name": "7YAE end-to-end test",
    "input": {
        "mode": "protein_ligands",
        "protein_file_id": protein_file_id,
        "ligand_file_ids": [ligand_file_id],
    },
    "parameterization": {
        "ph": 7.4,
        "padding_nm": 1.0,
        "ionic_strength_molar": 0.15,
    },
    "minimization": {
        "enabled": True,
        "max_iterations": 0,
        "tolerance_kj_mol_nm": 10.0,
    },
    "equilibration": [
        {
            "label": "NVT",
            "duration_ps": 1.0,
            "report_interval": 500,
            "trajectory_interval": 500,
            "checkpoint_interval": 500,
            "retries": 0,
            "velocity_seed": 1,
            "integrator": {
                "type": "langevin_middle",
                "timestep_ps": 0.002,
                "temperature_k": 300.0,
                "friction_per_ps": 1.0,
                "random_seed": 1,
            },
            "barostat": {"type": "none"},
        }
    ],
    "production": {
        "enabled": True,
        "label": "Production",
        "duration_ns": 0.001,
        "report_interval": 500,
        "trajectory_interval": 2500,
        "checkpoint_interval": 2500,
        "retries": 0,
        "retry_delay_s": 5.0,
        "integrator": {
            "type": "langevin_middle",
            "timestep_ps": 0.002,
            "temperature_k": 300.0,
            "friction_per_ps": 1.0,
            "random_seed": 1,
        },
        "barostat": {
            "type": "monte_carlo",
            "pressure_bar": 1.0,
            "temperature_k": 300.0,
            "frequency": 25,
            "random_seed": 1,
        },
    },
}

status, result = api_request("POST", "/api/v1/jobs/validate", body=payload)
print(f"Validate status: {status}")
if status != 200:
    print(f"FAILED: {result}")
    raise SystemExit(1)
print(f"Valid: {result['valid']}")
print(f"Config TOML length: {len(result['config_toml'])}")

# Step 4: Create job
print("\n=== Step 4: Create job ===")
status, result = api_request("POST", "/api/v1/jobs", body=payload)
print(f"Create status: {status}")
if status != 202:
    print(f"FAILED: {result}")
    raise SystemExit(1)
job_id = result["id"]
print(f"Job ID: {job_id}")
print(f"Status: {result['status']}")
print(f"Stages: {[s['name'] for s in result['stages']]}")

# Step 5: Poll for completion
print("\n=== Step 5: Poll job status ===")
import time
for i in range(60):
    status, result = api_request("GET", f"/api/v1/jobs/{job_id}")
    if status != 200:
        print(f"FAILED to get job: {result}")
        raise SystemExit(1)
    job_status = result["status"]
    phase = result.get("phase")
    current_stage = result.get("current_stage")
    progress = result.get("progress", {})
    pct = progress.get("percent")
    print(f"  [{i:2d}] status={str(job_status):12s} phase={str(phase):15s} stage={str(current_stage):15s} progress={pct}")
    if job_status in ("completed", "failed", "canceled"):
        break
    time.sleep(2)

if job_status != "completed":
    print(f"\nJob did not complete. Final status: {job_status}")
    if result.get("error"):
        print(f"Error: {result['error']}")
    raise SystemExit(1)

print("\nJob completed!")

# Step 6: List artifacts
print("\n=== Step 6: List artifacts ===")
status, result = api_request("GET", f"/api/v1/jobs/{job_id}/artifacts")
for artifact in result.get("items", []):
    print(f"  {artifact['kind']:15s} {artifact['relative_path']:60s} {artifact['size_bytes']:>10d} bytes")

# Step 7: Get config
print("\n=== Step 7: Get config ===")
status, result = api_request("GET", f"/api/v1/jobs/{job_id}/config", content_type="text/plain")
print(f"Config length: {len(result) if isinstance(result, str) else 'N/A'}")

print("\n=== E2E MD TEST PASSED ===")
