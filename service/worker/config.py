"""Environment-backed worker settings.

The worker never reads the API database and never accepts user-controlled
executables or paths.  Everything it needs comes from the environment plus the
claim response, and the claim response is validated before use.
"""

from __future__ import annotations

import os
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

WORKER_VERSION = "0.2.0"

WORKER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

RESTART_MODES = frozenset(
    {"resume", "restart", "restart_stage", "reparameterize"}
)


class ConfigError(ValueError):
    """Raised when the worker environment is not usable."""


def _env(
    env: dict[str, str], name: str, default: str | None = None
) -> str | None:
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
        raise ConfigError(f"{name} must be a number") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    return value


def _env_int(
    env: dict[str, str], name: str, default: int, *, minimum: int = 1
) -> int:
    raw = _env(env, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class WorkerConfig:
    """Runnable worker configuration."""

    api_url: str
    token: str
    worker_id: str
    hostname: str
    data_root: Path
    gpu_name: str | None = None
    gpu_uuid: str | None = None
    version: str = WORKER_VERSION
    simulate_path: Path = Path("/app/simulate.py")
    simulate_cwd: Path = Path("/app")
    poll_seconds: float = 2.0
    heartbeat_seconds: float = 10.0
    progress_poll_seconds: float = 2.0
    progress_send_seconds: float = 30.0
    cancel_grace_seconds: float = 30.0
    cancel_term_seconds: float = 10.0
    request_timeout_seconds: float = 30.0
    max_artifacts: int = 2000

    def validate(self) -> None:
        if not self.token:
            raise ConfigError("WORKER_TOKEN is required")
        if not WORKER_ID_RE.match(self.worker_id):
            raise ConfigError(
                "WORKER_ID must be 1-64 characters from A-Z, a-z, 0-9, "
                "dot, underscore, or hyphen, and must not start with a "
                "punctuation character"
            )
        parsed = urlsplit(self.api_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ConfigError("API_URL must be an absolute http(s) URL")
        if not self.hostname:
            raise ConfigError("the worker hostname must not be empty")
        if self.heartbeat_seconds > 60:
            raise ConfigError("WORKER_HEARTBEAT_SECONDS must be at most 60")

    @property
    def resolved_data_root(self) -> Path:
        return self.data_root.expanduser().resolve()

    @property
    def jobs_root(self) -> Path:
        """The directory that holds every account's job workspaces."""

        return self.resolved_data_root / "users"

    def job_root(self, owner_id: str, job_id: str) -> Path:
        """The workspace of one job of one account."""

        return self.jobs_root / owner_id / "jobs" / job_id


def load_config(
    env: dict[str, str] | None = None,
    *,
    hostname: str | None = None,
) -> WorkerConfig:
    """Build and validate settings from the process environment."""

    values = dict(os.environ if env is None else env)
    config = WorkerConfig(
        api_url=_env(values, "API_URL", "http://127.0.0.1:8000") or "",
        token=_env(values, "WORKER_TOKEN", "") or "",
        worker_id=_env(values, "WORKER_ID", "gpu-0") or "gpu-0",
        hostname=_env(values, "WORKER_HOSTNAME", hostname or socket.gethostname())
        or "",
        data_root=Path(_env(values, "DATA_ROOT", "/data") or "/data"),
        gpu_name=_env(values, "WORKER_GPU_NAME"),
        gpu_uuid=_env(values, "WORKER_GPU_UUID"),
        version=_env(values, "WORKER_VERSION", WORKER_VERSION) or WORKER_VERSION,
        simulate_path=Path(
            _env(values, "SIMULATE_PATH", "/app/simulate.py") or "/app/simulate.py"
        ),
        simulate_cwd=Path(_env(values, "SIMULATE_CWD", "/app") or "/app"),
        poll_seconds=_env_float(
            values, "WORKER_POLL_SECONDS", 2.0, minimum=0.1
        ),
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
        max_artifacts=_env_int(
            values, "WORKER_MAX_ARTIFACTS", 2000, minimum=1
        ),
    )
    config.validate()
    return config
