#!/usr/bin/env python3
"""Atomic live-progress document written by ``simulate.py``.

The service worker polls this file while a job runs.  Writes use a temporary
file plus ``Path.replace`` so a reader never sees a partial document.  Progress
is observational: a failed write is reported once and never aborts a simulation,
because the authoritative per-stage record remains ``stage.json``.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROGRESS_PHASES = frozenset(
    {
        "starting",
        "parameterizing",
        "minimizing",
        "simulating",
        "completed",
        "failed",
        "canceled",
    }
)

PROGRESS_STATUSES = frozenset({"running", "completed", "failed", "canceled"})


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


class ProgressWriter:
    """Best-effort writer for the worker's ``progress.json``.

    ``path=None`` disables all writes, which keeps manual CLI runs unchanged.
    Documents are merged so callers can update only the fields that changed.
    """

    def __init__(self, path: str | Path | None) -> None:
        self.path = Path(path).expanduser() if path is not None else None
        self._data: dict[str, Any] = {}
        self._disabled = self.path is None

    @property
    def enabled(self) -> bool:
        return not self._disabled

    def write(self, **fields: Any) -> None:
        """Replace the document with *fields*."""
        if self._disabled:
            return
        data = self._normalize(fields)
        self._data = data
        self._flush(data)

    def update(self, **fields: Any) -> None:
        """Merge *fields* into the current document."""
        if self._disabled:
            return
        data = dict(self._data)
        data.update(self._normalize(fields))
        self._data = data
        self._flush(data)

    def _normalize(self, fields: dict[str, Any]) -> dict[str, Any]:
        data = dict(fields)
        if "percent" in data:
            percent = _finite(data["percent"])
            data["percent"] = (
                None
                if percent is None
                else min(100.0, max(0.0, percent))
            )
        data["updated_at"] = utc_now()
        return data

    def _flush(self, data: dict[str, Any]) -> None:
        assert self.path is not None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(self.path.name + ".tmp")
            temporary.write_text(
                json.dumps(data, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError as exc:
            self._disabled = True
            print(
                f"Warning: could not write progress file {self.path}: {exc}",
                file=sys.stderr,
                flush=True,
            )
