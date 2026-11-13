"""Live smoke test of the account model against a running API.

Registers two accounts, signs them in, uploads a file with each, and checks
that neither can see the other's data, and that the files landed in the
per-account directories.

Run it inside the api container, where the data root and the database are
mounted at the paths the service uses::

    docker compose -f service/compose.yml run --rm --no-deps api \\
        python /app/scripts/smoke_accounts.py

It works on a throwaway database and data root, so it never touches the
deployment's own.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.session import CSRF_COOKIE  # noqa: E402
from app.settings import Settings  # noqa: E402

PDB = b"HEADER\nATOM      1  N   ALA A   1       0.000   0.000   0.000\nEND\n"

LAB_PASSWORD = "the old lab password"


def _csrf(client: TestClient) -> dict[str, str]:
    """The header a cookie-authenticated mutation has to carry."""

    token = client.cookies.get(CSRF_COOKIE)
    assert token, "the session did not set a CSRF cookie"
    return {"X-CSRF-Token": token}


def _register(
    client: TestClient, email: str, first: str, last: str
) -> dict | None:
    """Create an account.  The response signs the new account in."""

    response = client.post(
        "/api/v1/users",
        json={
            "email": email,
            "first_name": first,
            "last_name": last,
            "password": "correct horse battery",
        },
    )
    if response.status_code != 201:
        print(f"registration failed for {email}: {response.text}")
        return None
    return response.json()


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="md-accounts-"))
    failures: list[str] = []
    try:
        settings = Settings(
            database_url=f"sqlite:///{workdir / 'app.db'}",
            data_root=workdir / "data",
            service_api_token="smoke-token",
            worker_token="smoke-worker-token",
            web_password=LAB_PASSWORD,
            web_session_secret="smoke-session-secret",
            web_cookie_secure=False,
            simulation_platform="CPU",
            registration_enabled=True,
        )

        from alembic import command
        from alembic.config import Config

        api_dir = Path(__file__).resolve().parents[1]
        config = Config(str(api_dir / "alembic.ini"))
        config.set_main_option("script_location", str(api_dir / "alembic"))

        # The migration environment reads the database URL and the
        # administrator's password from the environment, and prefers them
        # over the programmatic settings.  Point the URL at the throwaway
        # database, and clear the configured hashes so the migration falls
        # back to the lab password below -- otherwise it would seed the
        # throwaway administrator with the deployment's own hash.
        overrides = {
            "DATABASE_URL": settings.database_url,
            "ADMIN_PASSWORD_HASH": "",
            "WEB_PASSWORD_HASH": "",
            "WEB_PASSWORD": LAB_PASSWORD,
        }
        previous = {name: os.environ.get(name) for name in overrides}
        os.environ.update(overrides)
        try:
            command.upgrade(config, "head")
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value

        app = create_app(settings)
        owner_dirs: list[str] = []

        with TestClient(app) as client:
            # 1. The administrator exists and can sign in with the lab
            #    password the deployment had before accounts existed.
            login = client.post(
                "/api/v1/session",
                json={
                    "email": settings.admin_email,
                    "password": LAB_PASSWORD,
                },
            )
            if login.status_code != 200:
                failures.append(f"admin sign-in failed: {login.status_code}")
            elif login.json().get("user", {}).get("is_admin") is not True:
                failures.append("the migrated account is not an administrator")

            client.cookies.clear()

            # 2. The first person registers and uploads a file.
            ada = _register(client, "ada@example.com", "Ada", "Lovelace")
            if ada is None:
                print("\n".join(failures))
                return 1

            ada_file = client.post(
                "/api/v1/files",
                headers=_csrf(client),
                files={"file": ("ada.pdb", PDB, "chemical/x-pdb")},
            )
            if ada_file.status_code != 201:
                failures.append(
                    f"ada's upload failed: {ada_file.status_code}"
                )
                ada_file_id = ""
            else:
                ada_file_id = ada_file.json()["id"]

            # The upload belongs to the account that is signed in.
            described = client.get("/api/v1/session").json()
            if described.get("owner") != ada["id"]:
                failures.append("the session does not belong to the new account")

            # 3. The second person registers.  Registering replaces the
            #    session, so the client is now the second account.
            client.cookies.clear()
            grace = _register(client, "grace@example.com", "Grace", "Hopper")
            if grace is None:
                print("\n".join(failures))
                return 1

            # 4. The second account cannot see the first account's file.
            if ada_file_id:
                hidden = client.get(f"/api/v1/files/{ada_file_id}")
                if hidden.status_code != 404:
                    failures.append(
                        f"grace could read ada's file: {hidden.status_code}"
                    )

            # 5. The files live in the per-account directories.  Only an
            #    account that produced something has a directory, so the
            #    second account has none yet.
            uploads = settings.data_root / "users"
            owner_dirs = sorted(p.name for p in uploads.iterdir())
            if owner_dirs != [ada["id"]]:
                failures.append(
                    f"expected only ada's directory, found {owner_dirs}"
                )

            grace_dir = uploads / grace["id"]
            if grace_dir.exists():
                failures.append("grace has a directory without having produced data")

            ada_dir = uploads / ada["id"] / "uploads"
            if not list(ada_dir.glob("*/*.pdb")):
                failures.append("ada's upload is not in her own directory")

        if failures:
            print("FAILURES:")
            for failure in failures:
                print(f"  - {failure}")
            return 1

        print("OK: two accounts registered, signed in, and stayed isolated.")
        print(f"    account directories: {owner_dirs}")
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
