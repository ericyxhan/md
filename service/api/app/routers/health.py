"""Health and readiness endpoints (unauthenticated)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ..errors import error_body

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request):
    settings = request.app.state.settings
    storage = request.app.state.storage
    checks: dict[str, str] = {}
    failures: list[str] = []

    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover - defensive
        checks["database"] = f"error: {exc}"
        failures.append("database")

    try:
        with request.app.state.session_factory() as session:
            version = session.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        if version is None:
            raise RuntimeError("alembic_version is empty")
        checks["migrations"] = str(version)
    except Exception as exc:  # pragma: no cover - defensive
        checks["migrations"] = f"error: {exc}"
        failures.append("migrations")

    try:
        storage.ensure_layout()
        with tempfile.NamedTemporaryFile(
            prefix=".readiness-", dir=storage.root
        ) as handle:
            handle.write(b"ok")
            handle.flush()
        checks["data_root"] = "ok"
    except Exception as exc:  # pragma: no cover - defensive
        checks["data_root"] = f"error: {exc}"
        failures.append("data_root")

    if failures:
        body = error_body(
            "not_ready",
            "Service is not ready",
            {"checks": checks, "failed": failures},
        )
        return JSONResponse(status_code=503, content=body)
    return {"status": "ok", "checks": checks, "data_root": str(settings.data_root)}
