"""Public file API tests."""

from __future__ import annotations

import hashlib
import json

from app.settings import Settings
from conftest import job_workspace, owner_root


def test_auth_is_required(client) -> None:
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"

    response = client.get(
        "/api/v1/capabilities", headers={"Authorization": "Bearer wrong"}
    )
    assert response.status_code == 401


def test_upload_and_metadata(client, auth, upload) -> None:
    content = b"HEADER test\nATOM      1  N   ALA A   1\n"
    response = upload("complex.pdb", content)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "complex.pdb"
    assert body["size_bytes"] == len(content)
    assert body["sha256"] == hashlib.sha256(content).hexdigest()
    assert body["content_type"] == "chemical/x-pdb"

    metadata = client.get(f"/api/v1/files/{body['id']}", headers=auth)
    assert metadata.status_code == 200
    assert metadata.json()["id"] == body["id"]


def test_upload_rejects_unsupported_suffix(client, upload) -> None:
    response = upload("script.sh", b"#!/bin/sh\necho hi\n")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_upload_rejects_empty_file(client, upload) -> None:
    response = upload("empty.pdb", b"")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "empty_upload"


def test_upload_enforces_size_limit(client, settings: Settings, upload) -> None:
    settings.max_upload_bytes = 8
    response = upload("too-big.pdb", b"x" * 9)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"

    stem = owner_root(settings) / "uploads"
    leftovers = list(stem.rglob("*.part")) if stem.exists() else []
    assert leftovers == []


def test_unknown_file_is_404(client, auth) -> None:
    response = client.get("/api/v1/files/not-a-real-id", headers=auth)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "file_not_found"


def test_preview_serves_upload_inline(client, auth, upload) -> None:
    content = b"HEADER test\nATOM      1  N   ALA A   1\n"
    file_id = upload("complex.pdb", content).json()["id"]

    unauthenticated = client.get(f"/api/v1/files/{file_id}/preview")
    assert unauthenticated.status_code == 401

    response = client.get(f"/api/v1/files/{file_id}/preview", headers=auth)
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"].startswith("chemical/x-pdb")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "attachment" not in response.headers.get("content-disposition", "")


def test_preview_rejects_oversized_uploads(
    client, settings: Settings, auth, upload
) -> None:
    settings.max_preview_bytes = 8
    file_id = upload("large.pdb", b"x" * 16).json()["id"]

    response = client.get(f"/api/v1/files/{file_id}/preview", headers=auth)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "file_too_large_to_preview"
    assert response.json()["error"]["details"]["size_bytes"] == 16


def _solvated_pdb(waters: int = 200) -> bytes:
    """A small protein plus a block of water."""

    lines = ["HEADER    SOLVATED"]
    for index in range(1, 11):
        lines.append(
            f"ATOM  {index:5d}  N   ALA A{index:4d}      "
            f"{index:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00  0.00           N"
        )
    for index in range(waters):
        lines.append(
            f"HETATM{index + 1:5d}  O   HOH W{index + 1:4d}      "
            f"{20.0 + index * 0.1:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00  0.00           O"
        )
    lines.append("END")
    return ("\n".join(lines) + "\n").encode()


def test_oversized_structure_gets_a_derived_solvent_free_preview(
    client, settings: Settings, auth, upload
) -> None:
    """A solvated system is too large to serve raw, but it can be previewed."""

    settings.max_preview_bytes = 64
    content = _solvated_pdb()
    file_id = upload("solvated.pdb", content).json()["id"]

    response = client.get(f"/api/v1/files/{file_id}/preview", headers=auth)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("chemical/x-pdb")

    body = response.content.decode()
    assert "ALA" in body
    assert "HOH" not in body
    # The protein survives, the solvent does not.
    assert body.count("ATOM") == 10


def test_derived_preview_is_cached_and_stable(
    client, settings: Settings, auth, upload
) -> None:
    settings.max_preview_bytes = 64
    file_id = upload("solvated.pdb", _solvated_pdb()).json()["id"]

    first = client.get(f"/api/v1/files/{file_id}/preview", headers=auth)
    second = client.get(f"/api/v1/files/{file_id}/preview", headers=auth)
    assert first.status_code == 200
    assert first.content == second.content


def test_preview_head_request_reports_the_status(
    client, settings: Settings, auth, upload
) -> None:
    """The viewer asks for the headers first to catch a refusal."""

    settings.max_preview_bytes = 64
    file_id = upload("solvated.pdb", _solvated_pdb()).json()["id"]

    response = client.head(f"/api/v1/files/{file_id}/preview", headers=auth)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("chemical/x-pdb")


def test_preview_of_an_unparseable_oversized_file_is_refused(
    client, settings: Settings, auth, upload
) -> None:
    settings.max_preview_bytes = 8
    file_id = upload("junk.pdb", b"not a structure at all\n").json()["id"]

    response = client.get(f"/api/v1/files/{file_id}/preview", headers=auth)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "file_too_large_to_preview"


def test_preview_unknown_file_is_404(client, auth) -> None:
    response = client.get("/api/v1/files/not-a-real-id/preview", headers=auth)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "file_not_found"


def test_inspect_returns_structure_summary(client, auth, upload) -> None:
    content = (
        b"CRYST1   50.000   50.000   50.000  90.00  90.00  90.00 P 1\n"
        b"ATOM      1  N   ALA A   1       1.000   2.000   3.000  1.00 20.00           N\n"
        b"ATOM      2  CA  ALA A   1       2.000   3.000   4.000  1.00 20.00           C\n"
        b"ATOM      3  C   ALA A   1       3.000   4.000   5.000  1.00 20.00           C\n"
        b"ATOM      4  N   GLY A   2       4.000   5.000   6.000  1.00 20.00           N\n"
        b"ATOM      5  CA  GLY A   2       5.000   6.000   7.000  1.00 20.00           C\n"
        b"ATOM      6  N   VAL A   3       6.000   7.000   8.000  1.00 20.00           N\n"
        b"ATOM      7  N   ALA B   1       9.000  10.000  11.000  1.00 20.00           N\n"
        b"ATOM      8  CA  ALA B   1      10.000  11.000  12.000  1.00 20.00           C\n"
        b"HETATM    9  O   HOH A 101      13.000  14.000  15.000  1.00 20.00           O\n"
        b"HETATM   10  CL   CL B 201      16.000  17.000  18.000  1.00 20.00          CL\n"
        b"HETATM   11  C1  LIG C 301      19.000  20.000  21.000  1.00 20.00           C\n"
        b"END\n"
    )
    file_id = upload("complex.pdb", content).json()["id"]

    response = client.get(f"/api/v1/files/{file_id}/inspect", headers=auth)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["atom_count"] == 11
    assert data["model_count"] == 1
    assert "A" in data["chains"]
    assert "B" in data["chains"]
    assert "C" in data["chains"]
    assert "ALA" in data["chains"]["A"]["residues"]
    assert "GLY" in data["chains"]["A"]["residues"]
    assert "VAL" in data["chains"]["A"]["residues"]
    assert "HOH" in data["chains"]["A"]["residues"]
    assert "ALA" in data["chains"]["B"]["residues"]
    assert "CL" in data["chains"]["B"]["residues"]
    assert "LIG" in data["chains"]["C"]["residues"]
    assert "LIG" in data["ligands"]
    assert data["components"]["protein"] == 8  # ALA(3)+GLY(2)+VAL(1)+ALA(2)
    assert data["components"]["water"] == 1
    assert data["components"]["ion"] == 1
    assert data["components"]["ligand"] == 1
    assert data["bounding_box"] is not None
    assert data["bounding_box"]["min"]["x"] == 1.0
    assert data["bounding_box"]["max"]["x"] == 19.0


def test_inspect_unknown_file_is_404(client, auth) -> None:
    response = client.get("/api/v1/files/not-a-real-id/inspect", headers=auth)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "file_not_found"


def test_inspect_rejects_non_pdb(client, auth, upload) -> None:
    file_id = upload("ligand.sdf", b"test sdf content").json()["id"]
    response = client.get(f"/api/v1/files/{file_id}/inspect", headers=auth)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_file_type"


# ---------------------------------------------------------------------------
# Analysis series endpoint
# ---------------------------------------------------------------------------


def _register_artifact(app, job_id: str, relative_path: str, kind: str) -> None:
    from app.models import Artifact

    with app.state.session_factory() as session:
        record = Artifact(
            id="test-artifact-id",
            job_id=job_id,
            stage_name=None,
            kind=kind,
            relative_path=relative_path,
            size_bytes=100,
            content_type="application/json",
            created_at="2026-01-01T00:00:00Z",
        )
        session.add(record)
        session.commit()


def test_series_endpoint_returns_downsampled_points(
    client, auth, upload, app, settings: Settings
) -> None:
    file = upload("complex.pdb").json()
    from conftest import job_payload

    payload = job_payload(file["id"])
    response = client.post("/api/v1/jobs", headers=auth, json=payload)
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]

    root = job_workspace(settings, job_id)
    analysis_dir = root / "outputs" / "analysis"
    analysis_dir.mkdir(parents=True)

    points = [
        {"step": i, "temperature_k": 300.0 + i, "potential_energy_kj_mol": -5000.0 - i}
        for i in range(5)
    ]
    series_data = {
        "group": "production",
        "source": "outputs/stages/production/simulation.log",
        "source_points": 5,
        "view_points": 5,
        "columns": ["step", "temperature_k", "potential_energy_kj_mol"],
        "points": points,
    }
    (analysis_dir / "series.json").write_text(
        json.dumps(series_data), encoding="utf-8"
    )

    _register_artifact(
        app, job_id, "outputs/analysis/series.json", "analysis"
    )

    response = client.get(
        f"/api/v1/jobs/{job_id}/analysis/series", headers=auth
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["group"] == "production"
    assert data["source_points"] == 5
    assert data["view_points"] == 5
    assert len(data["points"]) == 5
    assert data["points"][0]["step"] == 0
    assert data["points"][0]["temperature_k"] == 300.0
    assert data["points"][0]["potential_energy_kj_mol"] == -5000.0


def test_series_endpoint_missing_is_404(client, auth, upload, app, settings: Settings) -> None:
    file = upload("complex.pdb").json()
    from conftest import job_payload

    payload = job_payload(file["id"])
    response = client.post("/api/v1/jobs", headers=auth, json=payload)
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]

    response = client.get(
        f"/api/v1/jobs/{job_id}/analysis/series", headers=auth
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "series_not_found"
