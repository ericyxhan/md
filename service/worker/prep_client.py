"""HTTP client for the internal prep-worker protocol."""

from __future__ import annotations

from typing import Any

import httpx


class PrepAPIError(Exception):
    """An error response from the internal prep API."""

    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"prep API error {status_code}: {body}")


class PrepClient:
    """Client for /internal/v1/prep/* endpoints."""

    def __init__(self, api_url: str, token: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=api_url,
            headers={
                "X-Worker-Token": token,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def claim_prep(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Claim the oldest queued prep job.  None when the queue is empty."""

        response = self._client.post("/internal/v1/prep/claim", json=payload)
        if response.status_code == 204:
            return None
        if response.status_code >= 400:
            raise PrepAPIError(response.status_code, response.json())
        return response.json()

    def progress(
        self, prep_job_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Report progress for a prep job."""

        response = self._client.post(
            f"/internal/v1/prep/{prep_job_id}/progress", json=payload
        )
        if response.status_code >= 400:
            raise PrepAPIError(response.status_code, response.json())
        return response.json()

    def finish(
        self, prep_job_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Mark a prep job as completed or failed."""

        response = self._client.post(
            f"/internal/v1/prep/{prep_job_id}/finish", json=payload
        )
        if response.status_code >= 400:
            raise PrepAPIError(response.status_code, response.json())
        return response.json()

    def heartbeat(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send a prep worker heartbeat."""

        response = self._client.post("/internal/v1/prep/heartbeat", json=payload)
        if response.status_code >= 400:
            raise PrepAPIError(response.status_code, response.json())
        return response.json()

    def close(self) -> None:
        self._client.close()
