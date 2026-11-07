#!/usr/bin/env python3
"""Download a file from an HTTP URL into a local directory."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import requests


def download_file(url: str, target_directory: str | Path) -> Path:
    """Download *url* into *target_directory* and return the written path."""
    target_dir = Path(target_directory).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(urlparse(url).path).name
    if not filename:
        raise ValueError(f"URL does not contain a filename: {url}")
    target = target_dir / filename
    temporary = target.with_name(target.name + ".part")

    try:
        with requests.get(url, stream=True, timeout=(10, 60)) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)

    print(f"Downloaded: {target}")
    return target
