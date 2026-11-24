"""Synthetic collection/receipt regressions; no application tests or PostgreSQL."""

import json
from dataclasses import asdict
from pathlib import Path

import ci_shard
import pytest
from ci_shard import Inventory, Selection, node_list, shard_for, successful_reports, write_json

pytest_plugins = ["pytester"]


def test_partition_is_disjoint_complete_deterministic_and_preserves_parameters() -> None:
    nodes = tuple(f"tests/test_example.py::test_case[{number}]" for number in range(300))
    groups = [tuple(node for node in nodes if shard_for(node) == shard) for shard in range(4)]
    assert all(groups)
    assert len({node for group in groups for node in group}) == len(nodes)
    assert sum(map(len, groups)) == len(nodes)
    assert node_list(list(reversed(nodes))) == tuple(reversed(nodes))
    with pytest.raises(ValueError, match="unique"):
        node_list([nodes[0], nodes[0]])


def test_inventory_digest_binds_order_commit_and_source(tmp_path: Path) -> None:
    nodes = ("tests/test_b.py::test_b", "tests/test_a.py::test_a")
    original = Inventory("a" * 40, "source", "application", nodes)
    path = tmp_path / "inventory.json"
    write_json(path, asdict(original))
    assert Inventory.read(path) == original
    for changed in [
        Inventory("b" * 40, "source", "application", nodes),
        Inventory(original.commit, "changed", "application", nodes),
        Inventory(original.commit, "source", "application", tuple(reversed(nodes))),
    ]:
        assert changed.digest() != original.digest()
    path.write_text('{"nodes":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected inventory fields"):
        Inventory.read(path)


def test_source_hash_includes_nonpython_fixture_and_deployment_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = tmp_path / "backend"
    paths = [
        backend / "src/studymate/module.py",
        backend / "tests/fixture.bin",
        tmp_path / "deployment/backend/config.toml",
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"original")
    monkeypatch.setattr(ci_shard, "tracked_files", lambda _backend: tuple(paths))
    original = ci_shard.source_digest(backend)
    application = ci_shard.application_digest(backend)
    for path in paths:
        path.write_bytes(b"changed")
        assert ci_shard.source_digest(backend) != original
        path.write_bytes(b"original")
    paths[1].write_bytes(b"fixture changed")
    assert ci_shard.application_digest(backend) == application


def test_actual_pytest_collection_and_reports_for_one_partition(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(ci_shard=Path(ci_shard.__file__).read_text(encoding="utf-8"))
    tests = pytester.path / "tests"
    tests.mkdir()
    (tests / "test_example.py").write_text(
        "\n".join(f"def test_{number}():\n    assert True\n" for number in range(20)),
        encoding="utf-8",
    )
    nodes = tuple(f"tests/test_example.py::test_{number}" for number in range(20))
    write_json(
        pytester.path / "inventory.json", asdict(Inventory("commit", "source", "app", nodes))
    )
    pytester.makeconftest("""
import json
from pathlib import Path
from ci_shard import Inventory, Selection
selector = Selection(Inventory.read(Path("inventory.json")), 0)
def pytest_configure(config):
    config.pluginmanager.register(selector, "synthetic-peerly-selection")
def pytest_sessionfinish():
    data = {"selected": selector.selected, "reports": selector.reports}
    Path("actual.json").write_text(json.dumps(data))
""")
    result = pytester.runpytest_subprocess("tests", "-q")
    expected = tuple(node for node in nodes if shard_for(node) == 0)
    result.assert_outcomes(passed=len(expected), deselected=len(nodes) - len(expected))
    actual = json.loads((pytester.path / "actual.json").read_text())
    assert actual["selected"] == list(expected)
    assert set(actual["reports"]) == set(expected)
    assert all(
        phases == [["setup", "passed"], ["call", "passed"], ["teardown", "passed"]]
        for phases in actual["reports"].values()
    )


def test_failed_skipped_duplicate_missing_and_extra_phases_reject() -> None:
    node = "tests/test_example.py::test_one"
    phases = [("setup", "passed"), ("call", "passed"), ("teardown", "passed")]
    assert successful_reports((node,), {node: phases})
    for changed in [
        [],
        phases[:-1],
        phases + phases,
        [("setup", "skipped")],
        [("setup", "passed"), ("call", "xfail"), ("teardown", "passed")],
    ]:
        assert not successful_reports((node,), {node: changed})
    assert not successful_reports((node,), {})
    assert not successful_reports((node,), {node: phases, node + "extra": phases})
    assert not successful_reports((node, node + "second"), {node + "second": phases, node: phases})


def test_collection_error_and_xpass_are_not_accepted(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(ci_shard=Path(ci_shard.__file__).read_text(encoding="utf-8"))
    pytester.makepyfile(
        test_example="""
import pytest
@pytest.mark.xfail(reason="synthetic unexpected success")
def test_one():
    pass
"""
    )
    pytester.makeconftest("""
import json
from pathlib import Path
from ci_shard import Selection
selector = Selection(None, None)
def pytest_configure(config):
    config.pluginmanager.register(selector, "synthetic-peerly-reports")
def pytest_sessionfinish():
    Path("actual.json").write_text(json.dumps(selector.reports))
""")
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(xpassed=1)
    actual = json.loads((pytester.path / "actual.json").read_text())
    assert any(phase == ["call", "xfail"] for phases in actual.values() for phase in phases)
    selector = Selection(None, None)
    report = pytest.CollectReport("tests", "failed", "synthetic", [])
    selector.pytest_collectreport(report)
    assert selector.collection_errors == 1


def test_actual_collection_drift_fails_before_execution(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(ci_shard=Path(ci_shard.__file__).read_text(encoding="utf-8"))
    tests = pytester.path / "tests"
    tests.mkdir()
    (tests / "test_actual.py").write_text(
        "def test_actual():\n    raise RuntimeError('must not run')\n"
    )
    inventory = Inventory("commit", "source", "app", ("tests/test_old.py::test_old",))
    write_json(pytester.path / "inventory.json", asdict(inventory))
    pytester.makeconftest("""
from pathlib import Path
from ci_shard import Inventory, Selection
def pytest_configure(config):
    config.pluginmanager.register(Selection(Inventory.read(Path("inventory.json")), 0))
""")
    result = pytester.runpytest_subprocess("tests", "-q")
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*Actual collection differs from frozen inventory*"])


@pytest.mark.parametrize("payload", [b"", b"backend/a.bin\0backend/a.bin\0", b"../outside.bin\0"])
def test_tracked_manifest_rejects_empty_duplicate_or_escape_without_reading_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: bytes
) -> None:
    import subprocess

    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "a.bin").write_bytes(b"fixture")
    completed: subprocess.CompletedProcess[bytes] = subprocess.CompletedProcess(
        args=["synthetic-tracked-manifest"], returncode=0, stdout=payload
    )
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: completed)
    with pytest.raises(ValueError, match=r"empty or duplicated|missing or escapes"):
        ci_shard.tracked_files(backend)
