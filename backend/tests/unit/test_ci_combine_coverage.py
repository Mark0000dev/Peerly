"""Real tiny coverage databases exercise aggregate integrity and the global gate."""

import runpy
from dataclasses import asdict
from pathlib import Path

import ci_combine_coverage
import pytest
from ci_combine_coverage import combine, verify_union
from ci_shard import SHARDS, Inventory, digest_file, read_object, shard_for, write_json
from coverage import Coverage


def artifact_tree(root: Path, *, complete_branches: bool = True) -> tuple[Inventory, Path]:
    backend = root / "backend"
    backend.mkdir()
    (backend / "pyproject.toml").write_text(
        '[tool.coverage.run]\nbranch=true\nsource=["studymate"]\n'
        "[tool.coverage.report]\nfail_under=95\n",
        encoding="utf-8",
    )
    package = backend / "studymate"
    package.mkdir()
    source = package / "sample.py"
    source.write_text(
        "def choose(flag):\n    if flag:\n        return 1\n    return 2\n", encoding="utf-8"
    )
    chosen: dict[int, str] = {}
    number = 0
    while len(chosen) < SHARDS:
        node = f"tests/test_synthetic.py::test_case[{number}]"
        chosen.setdefault(shard_for(node), node)
        number += 1
    inventory = Inventory("a" * 40, "source", "application", tuple(chosen.values()))
    write_json(backend / "inventory.json", asdict(inventory))
    artifacts = root / "artifacts"
    for shard in range(SHARDS):
        folder = artifacts / f"backend-shard-{shard}"
        folder.mkdir(parents=True)
        data = folder / "coverage.sqlite"
        coverage = Coverage(data_file=str(data), branch=True, source=[str(package)])
        coverage.start()
        namespace: dict[str, object] = runpy.run_path(str(source))
        function = namespace["choose"]
        if not callable(function):
            raise TypeError("Synthetic branch fixture is not callable")
        function(True)
        if complete_branches:
            function(False)
        coverage.stop()
        coverage.save()
        node = chosen[shard]
        write_json(
            folder / "result.json",
            {
                "shard": shard,
                "commit": inventory.commit,
                "source_sha256": inventory.source_sha256,
                "application_sha256": inventory.application_sha256,
                "inventory_sha256": inventory.digest(),
                "selected": [node],
                "reports": {
                    node: [["setup", "passed"], ["call", "passed"], ["teardown", "passed"]]
                },
                "pytest_exit": 0,
                "valid": True,
                "coverage_sha256": digest_file(data),
            },
        )
    return inventory, artifacts


def test_complete_disjoint_receipts_and_real_branch_databases_pass(tmp_path: Path) -> None:
    inventory, artifacts = artifact_tree(tmp_path)
    assert len(verify_union(artifacts, inventory)) == SHARDS


@pytest.mark.parametrize(
    "change",
    [
        "missing-shard",
        "wrong-id",
        "source",
        "commit",
        "inventory",
        "missing-node",
        "duplicate-node",
        "skip",
        "xfail",
        "missing-phase",
        "pytest-fail",
        "incomplete",
        "coverage-changed",
    ],
)
def test_aggregate_rejects_incomplete_or_mismatched_actual_results(
    tmp_path: Path, change: str
) -> None:
    inventory, artifacts = artifact_tree(tmp_path)
    path = artifacts / "backend-shard-0/result.json"
    value = read_object(path)
    selected = value["selected"]
    if not isinstance(selected, list) or not isinstance(selected[0], str):
        raise TypeError("Synthetic selected node missing")
    node = selected[0]
    modifications: dict[str, dict[str, object]] = {
        "wrong-id": {"shard": 1},
        "source": {"source_sha256": "other"},
        "commit": {"commit": "other"},
        "inventory": {"inventory_sha256": "other"},
        "missing-node": {"selected": []},
        "duplicate-node": {"selected": [node, node]},
        "skip": {"reports": {node: [["setup", "skipped"]]}},
        "xfail": {
            "reports": {node: [["setup", "passed"], ["call", "xfail"], ["teardown", "passed"]]}
        },
        "missing-phase": {"reports": {node: [["setup", "passed"], ["call", "passed"]]}},
        "pytest-fail": {"pytest_exit": 1},
        "incomplete": {"valid": False},
    }
    if change == "missing-shard":
        path.unlink()
    elif change == "coverage-changed":
        (path.parent / "coverage.sqlite").write_bytes(b"changed")
    else:
        value.update(modifications[change])
        write_json(path, value)
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_union(artifacts, inventory)


@pytest.mark.parametrize("complete", [True, False], ids=["above95", "below95"])
def test_real_coverage_combine_enforces_final_global95_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, complete: bool
) -> None:
    inventory, artifacts = artifact_tree(tmp_path, complete_branches=complete)
    backend = tmp_path / "backend"
    monkeypatch.setattr(ci_combine_coverage, "source_digest", lambda _backend: "source")
    monkeypatch.setattr(ci_combine_coverage, "application_digest", lambda _backend: "application")
    if complete:
        assert combine(
            backend, inventory.commit, backend / "inventory.json", artifacts
        ) == pytest.approx(100)
        assert read_object(backend / "sharded-coverage-receipt.json")["passed"] is True
    else:
        with pytest.raises(ValueError, match="below95"):
            combine(backend, inventory.commit, backend / "inventory.json", artifacts)
        assert read_object(backend / "sharded-coverage-receipt.json")["passed"] is False


def test_extra_artifact_and_line_only_database_reject(tmp_path: Path) -> None:
    from coverage import CoverageData

    inventory, artifacts = artifact_tree(tmp_path)
    extra = artifacts / "backend-shard-inventory"
    extra.mkdir()
    with pytest.raises(ValueError, match="exactly four"):
        verify_union(artifacts, inventory)
    extra.rmdir()
    folder = artifacts / "backend-shard-0"
    path = folder / "coverage.sqlite"
    data = CoverageData(basename=str(path))
    data.erase()
    data.add_lines({str(tmp_path / "backend/studymate/sample.py"): {1}})
    data.write()
    receipt = read_object(folder / "result.json")
    receipt["coverage_sha256"] = digest_file(path)
    write_json(folder / "result.json", receipt)
    with pytest.raises(ValueError, match="branch measurements"):
        verify_union(artifacts, inventory)


def test_foreign_source_and_lowered_threshold_reject_before_passing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventory, artifacts = artifact_tree(tmp_path)
    backend = tmp_path / "backend"
    monkeypatch.setattr(ci_combine_coverage, "source_digest", lambda _backend: "different")
    with pytest.raises(ValueError, match="source/commit"):
        combine(backend, inventory.commit, backend / "inventory.json", artifacts)
    monkeypatch.setattr(ci_combine_coverage, "source_digest", lambda _backend: "source")
    monkeypatch.setattr(ci_combine_coverage, "application_digest", lambda _backend: "application")
    config = backend / "pyproject.toml"
    config.write_text(config.read_text().replace("fail_under=95", "fail_under=0"))
    with pytest.raises(ValueError, match="gate must remain"):
        combine(backend, inventory.commit, backend / "inventory.json", artifacts)
    assert not (backend / "sharded-coverage-receipt.json").exists()
