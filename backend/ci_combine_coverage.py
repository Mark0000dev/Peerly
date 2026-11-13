"""Require exact four-way execution, then enforce combined branch coverage >=95%."""

from __future__ import annotations

import argparse
from pathlib import Path

from ci_shard import (
    SHARDS,
    Inventory,
    application_digest,
    digest_file,
    node_list,
    read_object,
    shard_for,
    source_digest,
    string_field,
    write_json,
)
from coverage import Coverage, CoverageData

COVERAGE_THRESHOLD = 95


def verify_reports(value: object, selected: tuple[str, ...]) -> None:
    if not isinstance(value, dict) or tuple(value) != selected:
        raise ValueError("Actual executed nodes differ from selected inventory")
    expected = [["setup", "passed"], ["call", "passed"], ["teardown", "passed"]]
    if any(phases != expected for phases in value.values()):
        raise ValueError("Missing/duplicate/failed/skipped actual test phases")


def verify_shard(directory: Path, inventory: Inventory, shard: int) -> tuple[str, ...]:
    value = read_object(directory / "result.json")
    if value.get("shard") != shard or type(value.get("shard")) is not int:
        raise ValueError("Missing/duplicate/incorrect shard identity")
    if value.get("valid") is not True or type(value.get("pytest_exit")) is not int:
        raise ValueError("Shard did not complete successfully")
    if value["pytest_exit"] != 0:
        raise ValueError("Shard pytest failed")
    fields = {
        "commit": inventory.commit,
        "source_sha256": inventory.source_sha256,
        "application_sha256": inventory.application_sha256,
        "inventory_sha256": inventory.digest(),
    }
    if any(string_field(value, key) != expected for key, expected in fields.items()):
        raise ValueError("Shard source/commit/inventory identity mismatch")
    selected = node_list(value.get("selected"))
    expected = tuple(node for node in inventory.nodes if shard_for(node) == shard)
    if selected != expected:
        raise ValueError("Shard selection differs from deterministic partition")
    verify_reports(value.get("reports"), selected)
    data = directory / "coverage.sqlite"
    if not data.is_file() or digest_file(data) != string_field(value, "coverage_sha256"):
        raise ValueError("Shard coverage database missing or changed")
    coverage = CoverageData(basename=str(data))
    coverage.read()
    if not coverage.has_arcs() or not coverage.measured_files():
        raise ValueError("Shard coverage lacks branch measurements")
    return selected


def verify_union(artifacts: Path, inventory: Inventory) -> list[Path]:
    directories = sorted(artifacts.iterdir())
    if {directory.name for directory in directories} != {
        "backend-shard-" + str(shard) for shard in range(SHARDS)
    }:
        raise ValueError("Expected exactly four current-run shard artifacts")
    union: list[str] = []
    files: list[Path] = []
    for shard in range(SHARDS):
        directory = artifacts / ("backend-shard-" + str(shard))
        union.extend(verify_shard(directory, inventory, shard))
        files.append(directory / "coverage.sqlite")
    if set(union) != set(inventory.nodes) or len(set(union)) != len(union):
        raise ValueError("Actual shard results are not an exact disjoint inventory union")
    return files


def combine(backend: Path, commit: str, inventory_path: Path, artifacts: Path) -> float:
    inventory = Inventory.read(inventory_path)
    if inventory.commit != commit or inventory.source_sha256 != source_digest(backend):
        raise ValueError("Aggregate source/commit differs from actual inventory")
    if inventory.application_sha256 != application_digest(backend):
        raise ValueError("Aggregate application source differs")
    files = verify_union(artifacts, inventory)
    destination = backend / ".coverage"
    if destination.exists():
        raise ValueError("Stale aggregate coverage data exists")
    coverage = Coverage(data_file=str(destination), config_file=str(backend / "pyproject.toml"))
    if coverage.get_option("run:branch") is not True:
        raise ValueError("Branch coverage must remain enabled")
    if coverage.get_option("report:fail_under") != COVERAGE_THRESHOLD:
        raise ValueError("The project coverage gate must remain exactly95")
    if coverage.get_option("run:source") != ["studymate"]:
        raise ValueError("The complete product coverage source must remain unchanged")
    coverage.combine(data_paths=[str(path) for path in files], strict=True, keep=True)
    coverage.save()
    percentage = coverage.report()
    coverage.xml_report(outfile=str(backend / "coverage.xml"))
    write_json(
        backend / "sharded-coverage-receipt.json",
        {
            "commit": commit,
            "application_sha256": inventory.application_sha256,
            "source_sha256": inventory.source_sha256,
            "inventory_sha256": inventory.digest(),
            "tests": len(inventory.nodes),
            "shards": SHARDS,
            "branch": True,
            "combined_coverage": percentage,
            "threshold": COVERAGE_THRESHOLD,
            "passed": percentage >= COVERAGE_THRESHOLD,
            "input_coverage": [
                {"shard": shard, "sha256": digest_file(path)} for shard, path in enumerate(files)
            ],
            "configuration": {
                "branch": True,
                "source": ["studymate"],
                "fail_under": COVERAGE_THRESHOLD,
                "pyproject_sha256": digest_file(backend / "pyproject.toml"),
            },
            "coverage_xml_sha256": digest_file(backend / "coverage.xml"),
        },
    )
    if percentage < COVERAGE_THRESHOLD:
        raise ValueError("Combined branch-aware coverage is below95%")
    return percentage


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    combine(Path.cwd(), args.commit, args.inventory, args.artifacts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
