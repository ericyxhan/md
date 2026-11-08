"""Load the pure-stdlib simulation ``config.py`` by path.

The API image copies ``config.py`` from the repository root.  During local
development the file lives at the repository root instead.  Importing it by
path keeps the service independent of the process working directory and avoids
copying the validation logic into a second source of truth.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType


def _candidate_paths() -> list[Path]:
    candidates: list[Path] = []
    configured = os.environ.get("SIMULATION_CONFIG_PATH")
    if configured:
        candidates.append(Path(configured))
    candidates.append(Path.cwd() / "config.py")
    # service/api/app/simulation_config.py -> repository root
    candidates.append(Path(__file__).resolve().parents[3] / "config.py")
    candidates.append(Path("/app/config.py"))
    return candidates


@lru_cache(maxsize=1)
def _simulation_config_module() -> ModuleType:
    for candidate in _candidate_paths():
        if not candidate.is_file():
            continue
        spec = importlib.util.spec_from_file_location(
            "_md_simulation_config", candidate
        )
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    searched = ", ".join(str(path) for path in _candidate_paths())
    raise RuntimeError(f"Could not find the simulation config.py; searched: {searched}")


def load_workflow_config(path: str | Path):
    """Call the simulation code's ``load_config`` on a generated TOML file."""

    return _simulation_config_module().load_config(path)
