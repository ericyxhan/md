"""Environment-backed prep worker settings."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


WORKER_VERSION = "0.2.0"

WORKER_ID_RE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"


class PrepConfigError(ValueError):
    """Raised when the prep worker environment is not usable."""


def _env(env: dict[str, str], name: str, default: str | None = None) -> str | None:
    value = env.get(name)
    return value if value else default


def _env_float(
    env: dict[str, str],
    name: str,
    default: float,
    *,
    minimum: float = 0.01,
) -> float:
    raw = _env(env, name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise PrepConfigError(f"{name} must be a number") from exc
    if value < minimum:
        raise PrepConfigError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class PrepConfig:
    """Runnable prep worker configuration."""

    api_url: str
    token: str
    worker_id: str
    hostname: str
    packmol_path: str
    data_root: Path = Path("/data")
    version: str = WORKER_VERSION
    poll_seconds: float = 2.0
    heartbeat_seconds: float = 10.0
    progress_poll_seconds: float = 2.0
    progress_send_seconds: float = 30.0
    cancel_grace_seconds: float = 30.0
    cancel_term_seconds: float = 10.0
    request_timeout_seconds: float = 30.0

    def validate(self) -> None:
        if not self.token:
            raise PrepConfigError("WORKER_TOKEN is required")
        import re
        if not re.match(WORKER_ID_RE, self.worker_id):
            raise PrepConfigError(
                "WORKER_ID must be 1-64 characters from A-Z, a-z, 0-9, "
                "dot, underscore, or hyphen, and must not start with a "
                "punctuation character"
            )
        parsed = urlsplit(self.api_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise PrepConfigError("API_URL must be an absolute http(s) URL")
        if not self.packmol_path:
            raise PrepConfigError("PACKMOL_PATH is required for prep worker")
        packmol = Path(self.packmol_path)
        if not packmol.is_file():
            raise PrepConfigError(f"PACKMOL_PATH not found: {self.packmol_path}")
        if not os.access(packmol, os.X_OK):
            raise PrepConfigError(f"PACKMOL_PATH not executable: {self.packmol_path}")

    @property
    def resolved_data_root(self) -> Path:
        return self.data_root.expanduser().resolve()

    def prep_root(self, owner_id: str, prep_job_id: str) -> Path:
        """The workspace of one preparation of one account.

        Every account has its own tree, so the workspace is addressed by
        the account as well as by the preparation.
        """

        return self.resolved_data_root / "users" / owner_id / "prep" / prep_job_id


def load_config(
    env: dict[str, str] | None = None,
    *,
    hostname: str | None = None,
) -> PrepConfig:
    """Build and validate settings from the process environment."""

    import os

    values = dict(os.environ if env is None else env)
    config = PrepConfig(
        api_url=_env(values, "API_URL", "http://127.0.0.1:8000") or "",
        token=_env(values, "WORKER_TOKEN", "") or "",
        worker_id=_env(values, "WORKER_ID", "prep-0") or "prep-0",
        hostname=_env(values, "WORKER_HOSTNAME", hostname or socket.gethostname())
        or "",
        packmol_path=_env(values, "PACKMOL_PATH", "") or "",
        data_root=Path(_env(values, "DATA_ROOT", "/data") or "/data"),
        version=_env(values, "WORKER_VERSION", WORKER_VERSION) or WORKER_VERSION,
        poll_seconds=_env_float(values, "WORKER_POLL_SECONDS", 2.0, minimum=0.1),
        heartbeat_seconds=_env_float(
            values, "WORKER_HEARTBEAT_SECONDS", 10.0, minimum=0.1
        ),
        progress_poll_seconds=_env_float(
            values, "WORKER_PROGRESS_POLL_SECONDS", 2.0, minimum=0.1
        ),
        progress_send_seconds=_env_float(
            values, "WORKER_PROGRESS_SEND_SECONDS", 30.0, minimum=1.0
        ),
        cancel_grace_seconds=_env_float(
            values, "WORKER_CANCEL_GRACE_SECONDS", 30.0, minimum=0.0
        ),
        cancel_term_seconds=_env_float(
            values, "WORKER_CANCEL_TERM_SECONDS", 10.0, minimum=0.0
        ),
        request_timeout_seconds=_env_float(
            values, "WORKER_REQUEST_TIMEOUT_SECONDS", 30.0, minimum=1.0
        ),
    )
    config.validate()
    return config
