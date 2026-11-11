"""Actual CLI dispatch/composition and SQL; only resource engine is schema-isolated."""

import argparse
import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.bootstrap_data_cli import dispatch
from studymate.infrastructure.bootstrap_data import runtime
from tests.integration.bootstrap_data.test_apply import counts
from tests.unit.bootstrap_data.data import batch, encoded

pytestmark = pytest.mark.integration


async def test_apply_command_uses_main_composition_and_returns_safe_real_results(
    identity_engine: AsyncEngine,
    database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Retain real PostgreSQL/transactions and main composition. Replace only the
    # engine construction so this command cannot touch the shared default schema.
    def isolated_engine(url: object, **options: object) -> AsyncEngine:
        assert str(url).startswith("postgresql+asyncpg://")
        assert options["pool_size"] == 1
        assert options["max_overflow"] == 0
        return identity_engine

    monkeypatch.setattr(runtime, "create_async_engine", isolated_engine)
    monkeypatch.setenv("DATABASE_URL", database_url)
    path = tmp_path / "synthetic.json"
    path.write_bytes(encoded())
    options = argparse.Namespace(command="apply", file=str(path))
    assert await dispatch(options) == 0
    first = capsys.readouterr()
    assert not first.err
    initial = json.loads(first.out)
    assert initial["status"] == "applied"
    assert initial["policies_created"] == len(batch().policies)
    assert initial["subjects_created"] == 1
    assert await dispatch(options) == 0
    replay = capsys.readouterr()
    result = json.loads(replay.out)
    assert result["status"] == "unchanged"
    assert result["terms_id"] == initial["terms_id"]
    assert result["privacy_id"] == initial["privacy_id"]
    assert result["catalogue_replayed"] is True
    assert "PRIVATE" not in first.out + replay.out
    assert "Synthetic" not in first.out + replay.out
    assert database_url not in first.out + replay.out
    assert await counts(identity_engine) == (2, 1, 1)

    assert initial["terms_version"] == "test-v1"
    assert initial["privacy_version"] == "test-v1"
    path.write_bytes(encoded().replace(b"test-v1", b"test-v2"))
    assert await dispatch(options) == 0
    newer = json.loads(capsys.readouterr().out)
    assert newer["terms_version"] == "test-v2"
    assert newer["privacy_version"] == "test-v2"
    assert newer["terms_id"] != initial["terms_id"]
    assert newer["privacy_id"] != initial["privacy_id"]
    path.write_bytes(encoded())
    assert await dispatch(options) == 0
    old_replay = json.loads(capsys.readouterr().out)
    assert old_replay["status"] == "unchanged"
    assert old_replay["terms_version"] == newer["terms_version"]
    assert old_replay["privacy_version"] == newer["privacy_version"]
    assert old_replay["terms_id"] == newer["terms_id"]
    assert old_replay["privacy_id"] == newer["privacy_id"]
    assert await counts(identity_engine) == (4, 1, 2)
