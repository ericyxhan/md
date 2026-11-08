"""Public file API tests."""

from __future__ import annotations

import hashlib

from app.settings import Settings


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

    stem = settings.data_root / "uploads"
    leftovers = list(stem.rglob("*.part")) if stem.exists() else []
    assert leftovers == []


def test_unknown_file_is_404(client, auth) -> None:
    response = client.get("/api/v1/files/not-a-real-id", headers=auth)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "file_not_found"
