"""Read the simulation's atomic progress file.

``simulate.py`` writes ``progress.json`` with a temporary file plus
``os.replace``, so a reader either sees the old document or the new one.  This
module only parses and normalizes; it never writes the file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

API_PHASES = frozenset(
    {"parameterizing", "minimizing", "simulating", "finalizing"}
)

# The progress file uses lifecycle names that are broader than the API's
# phase column.  Map them onto the four phases the API stores.
_PHASE_MAP = {
    "starting": "parameterizing",
    "parameterizing": "parameterizing",
    "preparing": "parameterizing",
    "minimizing": "minimizing",
    "minimization": "minimizing",
    "simulating": "simulating",
    "equilibration": "simulating",
    "production": "simulating",
    "finalizing": "finalizing",
    "completed": "finalizing",
    "failed": "finalizing",
    "canceled": "finalizing",
}


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float) and value.is_integer():
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return None
    return None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
    else:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _optional_text(value: Any, limit: int = 200) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text[:limit] if text else None


@dataclass(frozen=True)
class ProgressSnapshot:
    """Normalized subset of ``progress.json`` used for API updates."""

    phase: str | None
    status: str | None
    stage: str | None
    step: int | None
    total_steps: int | None
    percent: float | None
    updated_at: str | None
    error: str | None

    @property
    def change_key(self) -> tuple[Any, ...]:
        return (self.phase, self.stage, self.step, self.total_steps)

    @property
    def api_phase(self) -> str | None:
        if self.phase is None:
            return None
        mapped = _PHASE_MAP.get(self.phase)
        if mapped in API_PHASES:
            return mapped
        return None

    def api_payload(self, run_token: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"run_token": run_token}
        if self.api_phase is not None:
            payload["phase"] = self.api_phase
        if self.stage is not None:
            payload["stage"] = self.stage
        if self.step is not None:
            payload["step"] = self.step
        if self.total_steps is not None:
            payload["total_steps"] = self.total_steps
        percent = self.percent
        if percent is None and self.step is not None and self.total_steps:
            percent = min(100.0, max(0.0, 100.0 * self.step / self.total_steps))
        if percent is not None:
            payload["percent"] = min(100.0, max(0.0, percent))
        if self.updated_at is not None:
            payload["updated_at"] = self.updated_at
        return payload


def read_progress(path: Path) -> ProgressSnapshot | None:
    """Return the current snapshot, or ``None`` when it is absent or invalid."""

    path = Path(path)
    if path.is_symlink() or not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    return ProgressSnapshot(
        phase=_optional_text(data.get("phase")),
        status=_optional_text(data.get("status")),
        stage=_optional_text(data.get("stage"), limit=64),
        step=_optional_int(data.get("step")),
        total_steps=_optional_int(data.get("total_steps")),
        percent=_optional_float(data.get("percent")),
        updated_at=_optional_text(data.get("updated_at"), limit=32),
        error=_optional_text(data.get("error"), limit=4000),
    )
