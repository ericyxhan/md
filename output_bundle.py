#!/usr/bin/env python3
"""Directory layout and small file helpers for a workflow run.

Everything a run produces lives under one bundle root::

    outputs/
      inputs/       copies of the input structures
      logs/         parameterization and other human-readable logs
      metadata/     prepared system, config snapshot, manifests
      stages/       one directory per minimization/equilibration/production stage

The bundle intentionally knows nothing about OpenMM.  It only owns paths and
safe JSON/text writes, which keeps the simulation code easier to read.
"""

from __future__ import annotations

import filecmp
import json
import shutil
from pathlib import Path
from typing import Any


class OutputBundle:
    """Create and manage the directory layout for one workflow run."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.inputs = self.root / "inputs"
        self.logs = self.root / "logs"
        self.metadata = self.root / "metadata"
        self.stages = self.root / "stages"

        for directory in (self.inputs, self.logs, self.metadata, self.stages):
            directory.mkdir(parents=True, exist_ok=True)

    # -- Stages -----------------------------------------------------------

    def stage(self, name: str) -> Path:
        """Create and return the directory for one stage."""
        path = self.stages / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def clear_stage(self, name: str) -> None:
        """Remove every file produced by one stage."""
        path = self.stages / name
        if path.exists():
            shutil.rmtree(path)

    def clear_stages(self) -> None:
        """Remove every stage, including minimization."""
        if self.stages.exists():
            shutil.rmtree(self.stages)
        self.stages.mkdir(parents=True, exist_ok=True)

    # -- Small file helpers ----------------------------------------------

    def write_text(self, relative_path: str | Path, text: str) -> Path:
        """Write text below the bundle, creating parent directories."""
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_json(self, relative_path: str | Path, data: Any) -> Path:
        """Atomically write a JSON document below the bundle."""
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return path

    def read_json(self, relative_path: str | Path) -> Any | None:
        """Read a JSON document, returning ``None`` when it does not exist."""
        path = self.root / relative_path
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def copy_input(self, source: str | Path) -> Path:
        """Copy an input file into ``inputs/`` and return the bundle copy.

        If two different files share a name, a numeric suffix is added instead
        of silently overwriting the first one.
        """
        source_path = Path(source).expanduser().resolve()
        target = self.inputs / source_path.name

        if target.resolve() == source_path:
            return target

        index = 1
        while target.exists():
            if filecmp.cmp(source_path, target, shallow=False):
                return target
            index += 1
            target = self.inputs / f"{source_path.stem}-{index}{source_path.suffix}"

        shutil.copy2(source_path, target)
        return target
