"""Synthetic in-container probes; supplied on stdin, never baked into the image."""

import asyncio
import importlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

RUNTIME_UID = 10001


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def status(path: str) -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=2) as response:
            code: object = response.status
            if not isinstance(code, int):
                raise TypeError("HTTP response lacks integer status")
            return code
    except urllib.error.HTTPError as error:
        return error.code


def health(expected: int) -> None:
    deadline = time.monotonic() + 30
    while True:
        try:
            if status("/api/health") == HTTPStatus.OK:
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("API did not become live within30s")
        time.sleep(0.2)
    require(status("/api/ready") == expected, "Unexpected readiness status")


def runtime() -> None:
    from PIL import Image
    from pydantic import ValidationError

    for name in (
        "asyncpg",
        "studymate.email_worker",
        "studymate.media_worker",
        "studymate.requests_worker",
        "studymate.changes_worker",
        "studymate.server",
    ):
        require(importlib.import_module(name).__name__ == name, "Runtime import failed")

    settings = importlib.import_module("studymate.config")
    for name, required in (
        ("EmailWorkerSettings", {"database_url", "code_key", "envelope_key", "smtp"}),
        ("MediaWorkerSettings", {"database_url", "media"}),
        ("RequestsWorkerSettings", {"database_url"}),
        ("ChangesWorkerSettings", {"database_url"}),
    ):
        factory = getattr(settings, name)
        try:
            factory(_env_file=None)
        except ValidationError as error:
            missing = {detail["loc"][0] for detail in error.errors() if detail["type"] == "missing"}
            require(missing == required, "Unexpected worker missing-configuration fields")
        else:
            raise RuntimeError("Worker accepted missing configuration")

    require(os.getuid() == RUNTIME_UID, "Runtime must use nonroot identity10001")
    require(Image.new("RGB", (1, 1)).size == (1, 1), "Pillow operation failed")
    for name in ("pytest", "ruff", "mypy", "hatchling"):
        require(
            importlib.util.find_spec(name) is None,
            "Development/build dependency in runtime",
        )
    for path in (
        "/app/.env",
        "/app/.env.worker",
        "/app/.env.media-worker",
        "/app/.env.requests-worker",
        "/app/.env.changes-worker",
        "/app/tests",
        "/app/uv.lock",
        "/usr/local/bin/uv",
        "/usr/local/bin/codex",
    ):
        require(not Path(path).exists(), "Unexpected build/auth artifact in runtime")
    require(not os.access("/root", os.R_OK), "Root home must be inaccessible")
    for entry in Path("/app").rglob("*"):
        if entry.is_file():
            require(
                entry.suffix == ".py" or entry == Path("/app/alembic.ini"),
                "Non-allowlisted application file",
            )
    try:
        Path("/app/write-must-fail").write_text("synthetic")
    except OSError:
        pass
    else:
        raise RuntimeError("Application root is writable")
    with tempfile.TemporaryFile() as target:
        target.write(b"synthetic")
    require(
        not any(name.endswith("_API_KEY") for name in os.environ),
        "Unexpected API credential",
    )


def database() -> None:
    deadline = time.monotonic() + 30
    while True:
        try:
            with socket.create_connection(("postgres", 5432), timeout=1):
                return
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError("Disposable PostgreSQL did not become reachable") from None
            time.sleep(0.2)


def bootstrap_offline(path: str) -> None:
    require("DATABASE_URL" not in os.environ, "Offline command inherited database config")
    for arguments in (("schema",), ("validate", path)):
        result = subprocess.run(  # noqa: S603 - fixed interpreter/module with synthetic path only.
            (sys.executable, "-m", "studymate.bootstrap_data_cli", *arguments),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        require(result.returncode == 0 and not result.stderr, "Offline CLI failed")
        value = json.loads(result.stdout)
        require(isinstance(value, dict), "Offline CLI did not return a JSON object")
        require("SYNTHETIC_TEST_ONLY" not in result.stdout, "Offline output exposed policy body")
    # Separate fresh process proves the module's offline import boundary as well.
    result = subprocess.run(
        (
            sys.executable,
            "-c",
            (
                "import sys; from studymate.bootstrap_data_cli import main; "
                "assert main(['schema']) == 0; assert 'sqlalchemy' not in sys.modules; "
                "assert 'studymate.config' not in sys.modules"
            ),
        ),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    require(result.returncode == 0 and not result.stderr, "Offline import boundary failed")


def bootstrap_api(output: str) -> None:
    expected = json.loads(output)
    for kind in ("terms", "privacy"):
        with urllib.request.urlopen(
            "http://127.0.0.1:8000/api/v1/policies/" + kind, timeout=2
        ) as response:
            value = json.load(response)
        require(
            value["reference"]["id"] == expected[kind + "_id"], "Public policy identity differs"
        )
        require(
            value["reference"]["version"] == expected[kind + "_version"],
            "Public policy version differs",
        )
        require(
            value["content"] == "SYNTHETIC_TEST_ONLY_" + kind.upper() + "_NOT_FOR_PRODUCTION",
            "Public policy body differs",
        )
    require(
        status("/api/v1/subjects") == HTTPStatus.UNAUTHORIZED,
        "Catalogue authentication guard changed",
    )
    asyncio.run(bootstrap_rows())


async def bootstrap_rows() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.connect() as connection:
            for statement in (
                "SELECT count(*) FROM accounts",
                "SELECT count(*) FROM sessions",
                "SELECT count(*) FROM registration_receipts",
            ):
                count = await connection.scalar(text(statement))
                require(count == 0, "Bootstrap unexpectedly seeded student authority")
            result = await connection.execute(text("SELECT id, name FROM subjects"))
            rows = result.all()
            require(len(rows) == 1, "Unexpected imported catalogue size")
            require(
                str(rows[0][0]) == "00000000-0000-0000-0000-000000000200",
                "Catalogue identity differs",
            )
            require(rows[0][1] == "Synthetic Image Subject", "Catalogue source differs")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    match sys.argv[1:]:
        case ["health", expected]:
            health(int(expected))
        case ["runtime"]:
            runtime()
        case ["bootstrap-offline", path]:
            bootstrap_offline(path)
        case ["bootstrap-api", output]:
            bootstrap_api(output)
        case ["database"]:
            database()
        case _:
            raise SystemExit("Unknown synthetic probe")
