"""Build/smoke task-owned local containers; no registry login, host ports or providers."""

import argparse
import hashlib
import json
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("image_probe.py").read_text()
POSTGRES = "postgres:16.15@sha256:f9a7b9ebf6f56201f949db745e47bc423c0f0f8294bafe991cc10bf74b029657"
LABEL = "dev.peerly.ops01"
BOOTSTRAP_FIXTURE = Path(__file__).with_name("fixtures") / "bootstrap-synthetic.json"
BOOTSTRAP_TARGET = "/run/peerly-bootstrap-synthetic.json"
CONTAINER_TMP = Path("/tmp")  # noqa: S108 - bounded container tmpfs mount, not a host file.


def docker(
    *args: str, stdin: str | None = None, timeout: int = 90
) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("docker")
    if executable is None:
        raise RuntimeError("Docker CLI required")
    # Fixed executable; argv only, no shell. Arguments are local smoke inputs, never PR expressions.
    return subprocess.run(  # noqa: S603
        (executable, *args),
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def checked(*args: str, stdin: str | None = None, timeout: int = 90) -> str:
    result = docker(*args, stdin=stdin, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Docker operation {args[0]} failed (exit {result.returncode})")
    return result.stdout.strip()


def fingerprint() -> str:
    digest = hashlib.sha256()
    base = ROOT / "backend"
    files = [
        base / name
        for name in (
            "Dockerfile",
            ".dockerignore",
            "pyproject.toml",
            "uv.lock",
            ".python-version",
            "alembic.ini",
        )
    ]
    files += sorted((base / "src").rglob("*.py")) + sorted((base / "migrations").rglob("*.py"))
    for path in files:
        digest.update(str(path.relative_to(base)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


@dataclass
class Smoke:
    image: str
    token: str = field(default_factory=lambda: "peerly-image-" + secrets.token_hex(6))
    containers: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    network_created: bool = False
    bootstrap_output: str = ""

    def common(self) -> tuple[str, ...]:
        return (
            "--read-only",
            "--tmpfs",
            f"{CONTAINER_TMP}:rw,noexec,nosuid,nodev,size=32m,mode=1777",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=64",
            "--memory=512m",
            "--cpus=1",
            "--log-driver=local",
            "--log-opt=max-size=1m",
            "--log-opt=max-file=2",
            "--label",
            LABEL + "=" + self.token,
        )

    def run(self, name: str, *args: str, stdin: str | None = None) -> str:
        full = self.token + "-" + name
        self.containers.append(full)
        return checked("run", "--name", full, *self.common(), *args, stdin=stdin)

    def probe(self, name: str, *args: str) -> None:
        checked("exec", "-i", self.token + "-" + name, "python", "-", *args, stdin=PROBE)

    def bootstrap_mount(self) -> tuple[str, ...]:
        return (
            "--mount",
            f"type=bind,src={BOOTSTRAP_FIXTURE.resolve()},dst={BOOTSTRAP_TARGET},readonly",
        )

    def basic(self) -> None:
        self.run(
            "bootstrap-offline",
            "--rm",
            "--network=none",
            "--no-healthcheck",
            *self.bootstrap_mount(),
            "-i",
            self.image,
            "python",
            "-",
            "bootstrap-offline",
            BOOTSTRAP_TARGET,
            stdin=PROBE,
        )
        self.outcomes.append("bootstrap_schema_validate_offline_no_env_no_network")

        self.run(
            "runtime",
            "--rm",
            "--network=none",
            "-i",
            "--no-healthcheck",
            self.image,
            "python",
            "-",
            "runtime",
            stdin=PROBE,
        )
        self.outcomes.append("nonroot_readonly_imports_production_dependencies")
        self.run(
            "down",
            "-d",
            "--network=none",
            "-e",
            "DATABASE_URL=postgresql+asyncpg://synthetic:synthetic@127.0.0.1:9/peerly_image_test",
            self.image,
        )
        self.probe("down", "health", "503")
        self.outcomes.append("health200_readiness503_without_database")
        checked("stop", "--time=10", self.token + "-down")
        for module in (
            "studymate.email_worker",
            "studymate.media_worker",
            "studymate.requests_worker",
            "studymate.changes_worker",
        ):
            name = self.token + "-" + module.rsplit(".", 1)[1]
            self.containers.append(name)
            result = docker(
                "run",
                "--rm",
                "--name",
                name,
                *self.common(),
                "--network=none",
                "--no-healthcheck",
                self.image,
                "python",
                "-m",
                module,
            )
            if result.returncode == 0 or '"runtime_error"' not in result.stdout + result.stderr:
                raise RuntimeError("Worker missing-configuration failure was not verified")
        self.outcomes.append("workers_fail_closed_without_configuration_no_network")
        self.run(
            "help",
            "--rm",
            "--network=none",
            "--no-healthcheck",
            self.image,
            "python",
            "-m",
            "studymate.server",
            "--help",
        )

    def database(self) -> str:
        checked("network", "create", "--internal", "--label", LABEL + "=" + self.token, self.token)
        self.network_created = True
        password = secrets.token_hex(24)
        db = self.token + "-postgres"
        self.containers.append(db)
        checked(
            "run",
            "-d",
            "--name",
            db,
            "--network",
            self.token,
            "--network-alias=postgres",
            "--label",
            LABEL + "=" + self.token,
            "--tmpfs",
            "/var/lib/postgresql/data:rw,nosuid,nodev,size=192m",
            "--memory=384m",
            "--cpus=1",
            "--pids-limit=96",
            "--log-driver=local",
            "--log-opt=max-size=1m",
            "--log-opt=max-file=2",
            "-e",
            "POSTGRES_USER=synthetic",
            "-e",
            "POSTGRES_PASSWORD=" + password,
            "-e",
            "POSTGRES_DB=peerly_image_test",
            POSTGRES,
        )
        url = "postgresql+asyncpg://synthetic:" + password + "@postgres:5432/peerly_image_test"
        self.run(
            "dbwait",
            "--rm",
            "--network",
            self.token,
            "--no-healthcheck",
            "-i",
            self.image,
            "python",
            "-",
            "database",
            stdin=PROBE,
        )
        for command in ("upgrade", "current"):
            args = ("head",) if command == "upgrade" else ()
            result = self.run(
                "migration-" + command,
                "--rm",
                "--network",
                self.token,
                "--no-healthcheck",
                "-e",
                "DATABASE_URL=" + url,
                self.image,
                "alembic",
                command,
                *args,
            )
        self.outcomes.append("empty_database_upgrade_head")
        self.bootstrap_data(url)
        self.authenticated_api(url)
        return result

    def bootstrap_data(self, url: str) -> None:
        results = []
        for action in ("apply", "replay"):
            output = self.run(
                "bootstrap-" + action,
                "--rm",
                "--network",
                self.token,
                "--no-healthcheck",
                *self.bootstrap_mount(),
                "-e",
                "DATABASE_URL=" + url,
                self.image,
                "python",
                "-m",
                "studymate.bootstrap_data_cli",
                "apply",
                BOOTSTRAP_TARGET,
            )
            value = json.loads(output)
            if value["status"] != ("applied" if action == "apply" else "unchanged"):
                raise RuntimeError("Unexpected bootstrap apply/replay result")
            if (
                value["terms_version"] != "image-test-v1"
                or value["privacy_version"] != "image-test-v1"
            ):
                raise RuntimeError("Bootstrap current policy versions differ")
            results.append(value)
        for key in ("terms_id", "privacy_id"):
            if results[0][key] != results[1][key]:
                raise RuntimeError("Bootstrap replay changed retained policy identity")
        if not results[1]["catalogue_replayed"] or results[1]["subjects_created"] != 0:
            raise RuntimeError("Bootstrap catalogue replay was not unchanged")
        self.bootstrap_output = json.dumps(results[1])
        self.outcomes.append(
            "explicit_mounted_synthetic_bootstrap_apply_replay_current_ids_versions"
        )

    def authenticated_api(self, url: str) -> None:
        auth = (
            "-e",
            "AUTHENTICATION__CLIENT_ID=synthetic-image-client",
            "-e",
            "AUTHENTICATION__CLIENT_SECRET=synthetic-not-real",
            "-e",
            "AUTHENTICATION__PUBLIC_ORIGIN=https://app.test",
            "-e",
            "AUTHENTICATION__ENVELOPE_KEY=" + secrets.token_hex(32),
            "-e",
            "AUTHENTICATION__BROWSER_SIGNING_KEY=" + secrets.token_hex(32),
            "-e",
            "AUTHENTICATION__CODE_KEY=" + secrets.token_hex(32),
        )
        self.run(
            "ready", "-d", "--network", self.token, "-e", "DATABASE_URL=" + url, *auth, self.image
        )
        self.probe("ready", "health", "200")
        self.probe("ready", "bootstrap-api", self.bootstrap_output)
        self.outcomes.append(
            "public_policy_current_ids_versions_catalogue_guard_unchanged_no_accounts_seeded"
        )
        self.outcomes.append("actual_auth_config_lifespan_readiness200_internal_network")
        checked("stop", "--time=10", self.token + "-ready")

    def cleanup(self) -> None:
        for name in reversed(self.containers):
            docker("rm", "-f", name)
        if self.network_created:
            checked("network", "rm", self.token)
        if checked("ps", "-aq", "--filter", "label=" + LABEL + "=" + self.token):
            raise RuntimeError("Owned smoke container cleanup incomplete")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="peerly-backend:local-check")
    parser.add_argument("--build", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(tempfile.gettempdir()) / "peerly-backend-image-smoke.json",
    )
    options = parser.parse_args()
    before = fingerprint()
    if options.build:
        checked(
            "build", "--progress=plain", "-t", options.image, str(ROOT / "backend"), timeout=600
        )
        if fingerprint() != before:
            raise RuntimeError("Source changed during build; rerun at a coherent owner checkpoint")
    checked("image", "inspect", options.image)
    checked("pull", POSTGRES, timeout=180)
    smoke = Smoke(options.image)
    started = time.monotonic()
    try:
        smoke.basic()
        head = smoke.database()
        if fingerprint() != before:
            raise RuntimeError("Source changed during smoke; rerun at a coherent owner checkpoint")
        evidence = {
            "image": options.image,
            "image_id": checked("image", "inspect", "--format", "{{.Id}}", options.image),
            "source_fingerprint": before,
            "source_stable_during_smoke": fingerprint() == before,
            "platform": checked(
                "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", options.image
            ),
            "migration_head": head,
            "checks": smoke.outcomes,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "published": False,
            "ai_enabled": False,
        }
    finally:
        smoke.cleanup()
    evidence["cleanup_verified"] = True
    options.output.write_text(json.dumps(evidence, indent=2) + "\n")
    sys.stdout.write(json.dumps(evidence, indent=2) + "\n")


if __name__ == "__main__":
    main()
