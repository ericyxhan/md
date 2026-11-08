"""Administrative retention cleanup.

Run from ``service/api`` with the same ``DATABASE_URL``, ``DATA_ROOT``, and
``RETENTION_DAYS`` as the API container:

    python -m app.cleanup --dry-run
    python -m app.cleanup

Retention is disabled unless ``RETENTION_DAYS`` is greater than zero.  Prefer
running this while the API and worker are idle, or use ``--dry-run`` first.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from .db import (
    create_db_engine,
    create_session_factory,
    ensure_database_directory,
)
from .services.maintenance import (
    cleanup_expired_jobs,
    cleanup_orphan_workspaces,
)
from .settings import get_settings
from .storage import LocalStorage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be removed without deleting anything",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    ensure_database_directory(settings)
    storage = LocalStorage(settings)
    storage.ensure_layout()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        expired = cleanup_expired_jobs(
            session_factory,
            storage,
            settings,
            dry_run=args.dry_run,
        )
        orphans = cleanup_orphan_workspaces(
            storage,
            settings,
            dry_run=args.dry_run,
        )
    finally:
        engine.dispose()

    print(
        json.dumps(
            {
                "dry_run": args.dry_run,
                "retention_days": settings.retention_days,
                "expired_jobs": asdict(expired),
                "orphan_workspaces": asdict(orphans),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
