#!/usr/bin/env python3
"""Check that every copy of a shared value still agrees.

``contract.env`` is the single source of truth for the values that more than
one file needs: the container ports, the service account, the mount paths and
the route prefixes.  The values are copied into compose.yml, the Caddyfile,
the Dockerfiles, the nginx config, the systemd units and the frontend, and a
copy that is edited without the others is silent until something breaks.

This script reads all of them and fails when they disagree, so the drift
shows up in a test run rather than as a 404 at the edge.

Two kinds of copy are accepted:

* a reference to the contract variable, e.g. ``${MD_API_PORT}`` or
  ``{$MD_API_PORT:8000}``, which cannot go stale on its own; and
* a literal, e.g. ``8000``, which is checked against the contract.

Where a reference carries a fallback, the fallback has to match the contract
too, so a build that runs without the contract file still produces the same
deployment.

Usage:
    python3 service/scripts/check-contract.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parents[1]
CONTRACT_FILE = SERVICE_DIR / "contract.env"

REQUIRED_KEYS = (
    "MD_API_PORT",
    "MD_WEB_PORT",
    "MD_EDGE_PORT",
    "MD_SERVICE_UID",
    "MD_SERVICE_GID",
    "MD_DATA_MOUNT",
    "MD_DB_MOUNT",
    "MD_API_PREFIX",
    "MD_INTERNAL_PREFIX",
)


class Report:
    """Collects the outcome of every check."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.checks = 0

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        self.checks += 1
        if ok:
            print(f"[PASS] {label}")
        else:
            print(f"[FAIL] {label}")
            if detail:
                for line in detail.splitlines():
                    print(f"       {line}")
            self.failures.append(label)
        return ok

    def equal(self, actual, expected, label: str, where: str) -> bool:
        return self.check(
            actual == expected,
            label,
            "" if actual == expected else f"expected {expected!r}, found {actual!r}\n  in {where}",
        )


def load_contract() -> dict[str, str]:
    """Parse the contract file into a plain mapping."""

    values: dict[str, str] = {}
    for raw in CONTRACT_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


PLACEHOLDER = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")


def resolve(value: str, contract: dict[str, str]) -> str:
    """Expand compose-style ``${VAR}`` and ``${VAR:-default}`` references."""

    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in contract:
            return contract[name]
        return default if default is not None else ""

    return PLACEHOLDER.sub(replace, value)


def references(value: str) -> set[str]:
    """Return the contract variables a value refers to."""

    return {match.group(1) for match in PLACEHOLDER.finditer(value)}


def report_value(
    report: Report,
    actual: object,
    expected: str,
    contract: dict[str, str],
    label: str,
    where: str,
) -> bool:
    """Compare a configured value with the contract, resolved.

    The value may be written literally or as a compose placeholder.  Either
    is accepted, but a placeholder's fallback has to agree with the contract
    as well, so that a plain ``docker compose`` without the contract file
    still produces the same deployment.
    """

    text = str(actual)
    resolved = resolve(text, contract)
    ok = resolved == expected
    detail = "" if ok else f"expected {expected!r}, found {resolved!r}\n  in {where}"

    for match in PLACEHOLDER.finditer(text):
        name, default = match.group(1), match.group(2)
        if default is None or name not in contract:
            continue
        if default != contract[name]:
            ok = False
            detail += (
                f"\nfallback for {name} is {default!r} but the contract says "
                f"{contract[name]!r}"
            )

    return report.check(ok, label, detail)


def report_arg(
    report: Report,
    text: str,
    name: str,
    expected: str,
    label: str,
    where: str,
) -> bool:
    """Check a Docker build argument default against the contract."""

    match = re.search(
        r"^ARG\s+" + re.escape(name) + r"=(\S*)\s*$", text, re.MULTILINE
    )
    if match is None:
        return report.check(
            False,
            label,
            f"no 'ARG {name}=...' declared\n  in {where}",
        )
    return report.equal(
        match.group(1), expected, label, where
    )


def report_uses(
    report: Report,
    text: str,
    needle: str,
    label: str,
    where: str,
) -> bool:
    """Check that a file refers to a contract variable instead of a literal."""

    return report.check(
        needle in text,
        label,
        "" if needle in text else f"expected {needle!r}\n  in {where}",
    )


def main() -> int:
    if not CONTRACT_FILE.exists():
        print(f"ERROR: contract file not found: {CONTRACT_FILE}", file=sys.stderr)
        return 2

    contract = load_contract()
    report = Report()

    missing = [key for key in REQUIRED_KEYS if key not in contract]
    if missing:
        print("[FAIL] contract.env defines every required key")
        for key in missing:
            print(f"       missing: {key}")
        return 1
    report.check(True, "contract.env defines every required key")

    api_port = contract["MD_API_PORT"]
    web_port = contract["MD_WEB_PORT"]
    edge_port = contract["MD_EDGE_PORT"]
    uid = contract["MD_SERVICE_UID"]
    gid = contract["MD_SERVICE_GID"]
    data_mount = contract["MD_DATA_MOUNT"]
    db_mount = contract["MD_DB_MOUNT"]
    api_prefix = contract["MD_API_PREFIX"]
    internal_prefix = contract["MD_INTERNAL_PREFIX"]

    # -- compose ----------------------------------------------------------
    compose_path = SERVICE_DIR / "compose.yml"
    try:
        import yaml
    except ImportError:
        yaml = None

    if yaml is not None:
        compose = yaml.safe_load(read(compose_path))
        if not isinstance(compose, dict):
            # A missing or unreadable compose file is a deployment problem,
            # not a reason to crash: report it and let the other checks run.
            report.check(
                False,
                "compose.yml could not be read",
                f"expected a mapping in {compose_path}",
            )
            compose = {}

        services = compose.get("services", {})

        api = services.get("api", {})
        report_value(
            report,
            (api.get("expose") or [""])[0],
            api_port,
            contract,
            "compose: api exposes the contract port",
            "service/compose.yml (api.expose)",
        )
        command = resolve(
            " ".join(str(part) for part in api.get("command", [])), contract
        )
        report.check(
            f"--port {api_port}" in command,
            "compose: api starts on the contract port",
            f"expected --port {api_port}\n  in service/compose.yml (api.command)",
        )
        healthcheck = resolve(
            " ".join(api.get("healthcheck", {}).get("test", [])), contract
        )
        report.check(
            f"127.0.0.1:{api_port}" in healthcheck,
            "compose: api healthcheck probes the contract port",
            f"expected 127.0.0.1:{api_port}\n  in service/compose.yml (api.healthcheck)",
        )
        report_value(
            report,
            api.get("environment", {}).get("DATA_ROOT"),
            data_mount,
            contract,
            "compose: api data root is the contract mount",
            "service/compose.yml (api.environment.DATA_ROOT)",
        )
        report.check(
            db_mount
            in resolve(
                api.get("environment", {}).get("DATABASE_URL", ""), contract
            ),
            "compose: api database url uses the contract mount",
            f"expected {db_mount} in DATABASE_URL\n  in service/compose.yml (api.environment)",
        )

        for name in ("worker", "prep-worker"):
            report_value(
                report,
                services.get(name, {}).get("environment", {}).get("API_URL"),
                f"http://api:{api_port}",
                contract,
                f"compose: {name} reaches the api on the contract port",
                f"service/compose.yml ({name}.environment.API_URL)",
            )

        web = services.get("web", {})
        report_value(
            report,
            (web.get("expose") or [""])[0],
            web_port,
            contract,
            "compose: web exposes the contract port",
            "service/compose.yml (web.expose)",
        )
        report_value(
            report,
            web.get("environment", {}).get("MD_WEB_PORT"),
            web_port,
            contract,
            "compose: web receives the contract port",
            "service/compose.yml (web.environment.MD_WEB_PORT)",
        )

        caddy = services.get("caddy", {})
        report_value(
            report,
            (caddy.get("ports") or [""])[0],
            f"127.0.0.1:{edge_port}:{edge_port}",
            contract,
            "compose: caddy publishes the contract port on loopback",
            "service/compose.yml (caddy.ports)",
        )
        caddy_env = caddy.get("environment", {})
        for key, value in (
            ("MD_EDGE_PORT", edge_port),
            ("MD_API_PORT", api_port),
            ("MD_WEB_PORT", web_port),
            ("MD_INTERNAL_PREFIX", internal_prefix),
        ):
            report_value(
                report,
                caddy_env.get(key),
                value,
                contract,
                f"compose: caddy receives {key}",
                f"service/compose.yml (caddy.environment.{key})",
            )

        # Build arguments: the images must be built as the contract account.
        for name in ("api", "migrate", "prep-worker"):
            build = services.get(name, {}).get("build", {})
            args = build.get("args", {})
            for key, value in (
                ("MD_SERVICE_UID", uid),
                ("MD_SERVICE_GID", gid),
            ):
                report_value(
                    report,
                    args.get(key),
                    value,
                    contract,
                    f"compose: {name} builds as the contract account ({key})",
                    f"service/compose.yml ({name}.build.args.{key})",
                )

        # Every bind mount that is not a named volume must target a contract
        # mount, so a rename cannot leave a container pointing at the wrong
        # directory.
        for name, service in services.items():
            for mount in service.get("volumes", []):
                if not isinstance(mount, str) or ":" not in mount:
                    continue
                target = resolve(mount.rsplit(":", 1)[1], contract)
                if target.startswith("/") and target not in (data_mount, db_mount):
                    if target in ("/data", "/config"):
                        continue  # Caddy's own storage
                    report.check(
                        False,
                        f"compose: {name} mounts on a contract path",
                        f"mount target {target!r} is not a contract mount\n"
                        f"  in service/compose.yml ({name}.volumes)",
                    )
    else:
        print("[SKIP] compose checks (pyyaml is not installed)")

    # -- Caddyfile --------------------------------------------------------
    caddyfile = read(SERVICE_DIR / "Caddyfile")
    for name, expected, label in (
        ("MD_EDGE_PORT", edge_port, "caddy: listen port"),
        ("MD_API_PORT", api_port, "caddy: api upstream port"),
        ("MD_WEB_PORT", web_port, "caddy: web upstream port"),
        ("MD_INTERNAL_PREFIX", internal_prefix, "caddy: blocked prefix"),
    ):
        match = re.search(
            r"\{\$" + re.escape(name) + r":([^}]*)\}", caddyfile
        )
        fallback = match.group(1) if match else None
        report.equal(
            fallback,
            expected,
            f"{label} fallback matches the contract",
            "service/Caddyfile",
        )

    # -- Dockerfiles ------------------------------------------------------
    api_dockerfile = read(SERVICE_DIR / "api" / "Dockerfile")
    prep_dockerfile = read(SERVICE_DIR / "worker" / "prep_worker.Dockerfile")
    web_dockerfile = read(SERVICE_DIR / "web" / "Dockerfile")

    for name, text, where in (
        ("api", api_dockerfile, "service/api/Dockerfile"),
        ("prep worker", prep_dockerfile, "service/worker/prep_worker.Dockerfile"),
    ):
        report_arg(
            report,
            text,
            "MD_SERVICE_UID",
            uid,
            f"dockerfile: {name} builds as the contract uid",
            where,
        )
        report_arg(
            report,
            text,
            "MD_SERVICE_GID",
            gid,
            f"dockerfile: {name} builds as the contract gid",
            where,
        )
        report_uses(
            report,
            text,
            "USER ${MD_SERVICE_UID}:${MD_SERVICE_GID}",
            f"dockerfile: {name} runs as the contract account",
            where,
        )
        report_arg(
            report,
            text,
            "MD_API_PORT",
            api_port,
            f"dockerfile: {name} exposes the contract port",
            where,
        )

    report_arg(
        report,
        web_dockerfile,
        "MD_WEB_PORT",
        web_port,
        "dockerfile: web exposes the contract port",
        "service/web/Dockerfile",
    )

    # -- nginx ------------------------------------------------------------
    nginx = read(SERVICE_DIR / "web" / "nginx.conf")
    report_uses(
        report,
        nginx,
        "listen ${MD_WEB_PORT};",
        "nginx: listens on the contract port",
        "service/web/nginx.conf",
    )

    # -- FastAPI route prefixes -------------------------------------------
    main_py = read(SERVICE_DIR / "api" / "app" / "main.py")
    report.check(
        f'prefix="{api_prefix}"' in main_py,
        "api: public router uses the contract prefix",
        f'expected prefix="{api_prefix}"\n  in service/api/app/main.py',
    )
    internal_py = read(SERVICE_DIR / "api" / "app" / "routers" / "internal.py")
    report.check(
        f'prefix="{internal_prefix}"' in internal_py,
        "api: internal router uses the contract prefix",
        f'expected prefix="{internal_prefix}"\n  in service/api/app/routers/internal.py',
    )

    # -- frontend ---------------------------------------------------------
    api_ts = read(SERVICE_DIR / "web" / "src" / "lib" / "api.ts")
    report.check(
        f'"{api_prefix}"' in api_ts,
        "frontend: calls the api on the contract prefix",
        f'expected "{api_prefix}"\n  in service/web/src/lib/api.ts',
    )

    # -- systemd templates -------------------------------------------------
    funnel_unit = read(SERVICE_DIR / "scripts" / "md-funnel.service")
    report_uses(
        report,
        funnel_unit,
        "http://127.0.0.1:${MD_EDGE_PORT}",
        "systemd: funnel targets the contract edge port",
        "service/scripts/md-funnel.service",
    )

    print()
    if report.failures:
        print(f"{len(report.failures)} of {report.checks} checks failed.")
        print("Every copy of a shared value lives in service/contract.env.")
        return 1
    print(f"All {report.checks} checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
