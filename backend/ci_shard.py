"""Optional four-shard CI: actual collection, fixed selection and execution receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import pytest

SHARDS = 4
MAX_JSON = 8 * 1024 * 1024


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_files(backend: Path) -> tuple[Path, ...]:
    repository = backend.parent.resolve()
    if not Path("/usr/bin/git").is_file():
        raise ValueError("Existing hosted /usr/bin/git executable is required")
    result = subprocess.run(
        [
            "/usr/bin/git",
            "ls-files",
            "-z",
            "--",
            "backend",
            "deployment",
            ".github/workflows/backend.yml",
            ".github/workflows/backend-sharded.yml",
        ],
        cwd=repository,
        capture_output=True,
        check=True,
        timeout=30,
    )
    names = result.stdout.decode("utf-8").split("\0")
    paths = tuple(repository / name for name in names if name)
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("Tracked source inventory is empty or duplicated")
    for path in paths:
        if not path.resolve().is_relative_to(repository) or not path.is_file():
            raise ValueError("Tracked source is missing or escapes checkout")
        if path.name == ".env":
            raise ValueError("Tracked private environment files are forbidden")
    return paths


def source_digest(backend: Path) -> str:
    rows = [
        (str(path.relative_to(backend.parent)), digest_file(path))
        for path in tracked_files(backend)
    ]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def application_digest(backend: Path) -> str:
    paths = tuple(
        path
        for path in tracked_files(backend)
        if path.is_relative_to(backend / "src") or path.is_relative_to(backend / "migrations")
    )
    rows = [(str(path.relative_to(backend)), digest_file(path)) for path in paths]
    if not rows:
        raise ValueError("Application source inventory is empty")
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def shard_for(nodeid: str) -> int:
    return int.from_bytes(hashlib.sha256(nodeid.encode()).digest()[:8]) % SHARDS


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def read_object(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        content = stream.read(MAX_JSON + 1)
    if len(content) > MAX_JSON:
        raise ValueError("CI receipt is oversized")
    value: object = json.loads(content)
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("CI receipt must be an object")
    return cast("dict[str, object]", value)


def string_field(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError("Missing CI string field: " + key)
    return item


def node_list(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("Missing collected test nodes")
    if any(not isinstance(node, str) or not node.startswith("tests/") for node in value):
        raise ValueError("Invalid test node")
    nodes = tuple(cast("list[str]", value))
    if len(set(nodes)) != len(nodes):
        raise ValueError("Test inventory must contain unique ordered nodes")
    return nodes


@dataclass(frozen=True, slots=True)
class Inventory:
    commit: str
    source_sha256: str
    application_sha256: str
    nodes: tuple[str, ...]

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    @classmethod
    def read(cls, path: Path) -> Inventory:
        value = read_object(path)
        if set(value) != {"commit", "source_sha256", "application_sha256", "nodes"}:
            raise ValueError("Unexpected inventory fields")
        return cls(
            string_field(value, "commit"),
            string_field(value, "source_sha256"),
            string_field(value, "application_sha256"),
            node_list(value["nodes"]),
        )


class Selection:
    def __init__(self, inventory: Inventory | None, shard: int | None) -> None:
        self.inventory = inventory
        self.shard = shard
        self.collected: tuple[str, ...] = ()
        self.selected: tuple[str, ...] = ()
        self.reports: dict[str, list[tuple[str, str]]] = {}
        self.collection_errors = 0

    def pytest_collection_modifyitems(
        self, config: pytest.Config, items: list[pytest.Item]
    ) -> None:
        self.collected = tuple(item.nodeid for item in items)
        if not self.collected or len(set(self.collected)) != len(items):
            raise pytest.UsageError("Collection must be nonempty with unique node IDs")
        if self.inventory is None:
            return
        if self.collected != self.inventory.nodes:
            raise pytest.UsageError("Actual collection differs from frozen inventory")
        selected = [item for item in items if shard_for(item.nodeid) == self.shard]
        deselected = [item for item in items if shard_for(item.nodeid) != self.shard]
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
        self.selected = tuple(item.nodeid for item in selected)
        if not self.selected:
            raise pytest.UsageError("Selected shard is empty")

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.failed or report.skipped:
            self.collection_errors += 1

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        outcome = "xfail" if hasattr(report, "wasxfail") else report.outcome
        self.reports.setdefault(report.nodeid, []).append((report.when, outcome))


def successful_reports(
    selected: tuple[str, ...], reports: dict[str, list[tuple[str, str]]]
) -> bool:
    expected = [("setup", "passed"), ("call", "passed"), ("teardown", "passed")]
    return (
        bool(selected)
        and tuple(reports) == selected
        and all(phases == expected for phases in reports.values())
    )


def collect(backend: Path, commit: str, output: Path) -> int:
    source = source_digest(backend)
    selector = Selection(None, None)
    status = pytest.main(["--collect-only", "-q"], plugins=[selector])
    if status != 0 or selector.collection_errors or source != source_digest(backend):
        return 1
    inventory = Inventory(commit, source, application_digest(backend), selector.collected)
    write_json(output, asdict(inventory))
    return 0


def execute(backend: Path, commit: str, inventory_path: Path, shard: int, output: Path) -> int:
    inventory = Inventory.read(inventory_path)
    if not 0 <= shard < SHARDS or inventory.commit != commit:
        raise ValueError("Shard/commit does not match this run")
    if inventory.source_sha256 != source_digest(backend):
        raise ValueError("Test/application/configuration source differs from inventory")
    output.mkdir(parents=True, exist_ok=True)
    coverage = backend / ".coverage"
    if coverage.exists():
        raise ValueError("Stale coverage database exists")
    selector = Selection(inventory, shard)
    status = pytest.main(
        [
            "--cov",
            "--cov-report=",
            "--cov-fail-under=0",
            "--junitxml=" + str(output / "junit.xml"),
        ],
        plugins=[selector],
    )
    valid = (
        status == 0
        and not selector.collection_errors
        and successful_reports(selector.selected, selector.reports)
        and inventory.source_sha256 == source_digest(backend)
        and coverage.is_file()
    )
    if coverage.is_file():
        coverage.rename(output / "coverage.sqlite")
    write_json(
        output / "result.json",
        {
            "shard": shard,
            "commit": commit,
            "source_sha256": inventory.source_sha256,
            "application_sha256": inventory.application_sha256,
            "inventory_sha256": inventory.digest(),
            "selected": selector.selected,
            "reports": selector.reports,
            "pytest_exit": int(status),
            "valid": valid,
            "coverage_sha256": digest_file(output / "coverage.sqlite")
            if (output / "coverage.sqlite").is_file()
            else "missing",
        },
    )
    return 0 if valid else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inventory", "run"))
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--shard", type=int)
    args = parser.parse_args()
    backend = Path.cwd().resolve()
    if os.environ.get("PYTEST_ADDOPTS") or os.environ.get("COVERAGE_FILE"):
        parser.error("Ambient test selectors or alternate coverage files are forbidden")
    if args.mode == "inventory":
        return collect(backend, args.commit, args.output)
    if args.inventory is None or args.shard is None:
        parser.error("run requires --inventory and --shard")
    return execute(backend, args.commit, args.inventory, args.shard, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
