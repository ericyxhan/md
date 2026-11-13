"""Create an account from the command line.

Useful when registration is switched off, and for provisioning the first
administrator of a fresh deployment.

Run it inside the api container, where the database is mounted::

    docker compose -f service/compose.yml run --rm --no-deps api \\
        python /app/scripts/create_account.py --email ada@example.com \\
        --first-name Ada --last-name Lovelace

Without ``--password`` a strong password is generated and printed once.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.exc import OperationalError  # noqa: E402

from app.db import create_db_engine, create_session_factory  # noqa: E402
from app.settings import Settings  # noqa: E402
from app.users import create_user  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    parser.add_argument(
        "--password",
        default="",
        help="the password; a strong one is generated when this is empty",
    )
    parser.add_argument(
        "--admin",
        action="store_true",
        help="make the account an administrator",
    )
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="create the account without letting it sign in yet",
    )
    arguments = parser.parse_args(argv)

    password = arguments.password or secrets.token_urlsafe(18)

    settings = Settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        with session_factory() as session:
            try:
                user = create_user(
                    session,
                    email=arguments.email,
                    first_name=arguments.first_name,
                    last_name=arguments.last_name,
                    password=password,
                    is_admin=arguments.admin,
                    is_active=not arguments.inactive,
                )
            except OperationalError as exc:
                if "users" in str(exc):
                    raise SystemExit(
                        "ERROR: the accounts table does not exist yet; run the "
                        "migrations first (alembic upgrade head)"
                    ) from exc
                raise
            session.commit()
            print(f"[create-account] account {user.email} created ({user.id})")
    finally:
        engine.dispose()

    if not arguments.password:
        print()
        print("===============================================")
        print(" New password (shown once):")
        print()
        print(f"   {password}")
        print()
        print(" Store it in your password manager now.")
        print("===============================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
