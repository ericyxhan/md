"""HTTP client for the internal worker protocol.

The worker never opens SQLite.  Every state change goes through the API and is
fenced by the run token returned from ``claim``.
"""

from __future__ import annotations

from typing import Any

import httpx


class WorkerAPIError(RuntimeError):
    def __init__(self, status_code: int, body: Any) -> None:
        super().__init__(f"API returned {status_code}: {body}")
        self.status_code = status_code
        self.body = body


class WorkerClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"X-Worker-Token": token},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "WorkerClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = response.text
            raise WorkerAPIError(response.status_code, body)
        return response

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/healthz").json()

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST", "/internal/v1/workers/heartbeat", json=payload
        ).json()

    def claim(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        response = self._request("POST", "/internal/v1/jobs/claim", json=payload)
        if response.status_code == 204:
            return None
        return response.json()

    def progress(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST", f"/internal/v1/jobs/{job_id}/progress", json=payload
        ).json()

    def stage(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST", f"/internal/v1/jobs/{job_id}/stage", json=payload
        ).json()

    def finish(self, job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST", f"/internal/v1/jobs/{job_id}/finish", json=payload
        ).json()
