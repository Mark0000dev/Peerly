"""Strict streamed native protocol/error regressions; no provider/PG/real credentials."""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from deployment.backup import streaming
from deployment.backup.retention import Retention
from deployment.backup.run_backup import Plan

NAME = "database/source.dump"
EXPECTED = {NAME: streaming.Expected(3, "a" * 64)}
GOOD = ("a" * 64 + "  " + NAME + "\n").encode()


def test_exact_hash_and_known_size_pass_without_raw_payload_copy() -> None:
    state = streaming.Hashes(EXPECTED)
    state.line(GOOD)
    state.finish(0)
    assert (
        streaming.listing(
            json.dumps([{"Path": NAME, "Size": 3, "IsDir": False}]).encode(), EXPECTED
        )
        == 0
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        GOOD[:-1],
        b"a" * 63 + b"  database/source.dump\n",
        b"A" * 64 + b"  database/source.dump\n",
        b"a" * 64 + b" *database/source.dump\n",
        b"a" * 64 + b"  ../source.dump\n",
        b"a" * 64 + b"  unexpected\n",
        b"a" * 64 + b"  database/source.dump\x00\n",
        b"x" * (streaming.MAX_HASH_LINE + 1),
    ],
)
def test_malformed_unknown_unsafe_and_unterminated_hash_lines_fail(raw: bytes) -> None:
    with pytest.raises(streaming.ReadbackError):
        streaming.Hashes(EXPECTED).line(raw)


def test_missing_duplicate_wronghash_and_partial_command_failure_are_not_success() -> None:
    with pytest.raises(streaming.ReadbackError, match="hash_missing"):
        streaming.Hashes(EXPECTED).finish(0)
    state = streaming.Hashes(EXPECTED)
    state.line(GOOD)
    with pytest.raises(streaming.ReadbackError, match="hash_file_set"):
        state.line(GOOD)
    with pytest.raises(streaming.ReadbackError, match="hash_command_failed"):
        state.finish(7)  # Even ALL expected lines cannot override a failed native command.
    with pytest.raises(streaming.ReadbackError, match="hash_mismatch"):
        streaming.Hashes(EXPECTED).line(GOOD.replace(b"a", b"b", 1))


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"Path": NAME, "Size": 3, "IsDir": False}] * 2,
        [{"Path": NAME, "Size": 4, "IsDir": False}],
        [{"Path": NAME, "Size": -2, "IsDir": False}],
        [{"Path": NAME, "Size": True, "IsDir": False}],
        [{"Path": NAME, "Size": 3, "IsDir": True}],
        [{"Path": "extra", "Size": 3, "IsDir": False}],
    ],
)
def test_listing_missing_duplicate_size_and_type_errors_fail(
    items: list[dict[str, object]],
) -> None:
    with pytest.raises(streaming.ReadbackError):
        streaming.listing(json.dumps(items).encode(), EXPECTED)


def test_unavailable_size_is_explicit_and_does_not_skip_hash_validation() -> None:
    assert (
        streaming.listing(
            json.dumps([{"Path": NAME, "Size": -1, "IsDir": False}]).encode(), EXPECTED
        )
        == 1
    )
    with pytest.raises(streaming.ReadbackError, match="hash_mismatch"):
        streaming.Hashes(EXPECTED).line(GOOD.replace(b"a", b"b", 1))


def test_duplicate_json_properties_are_not_silently_overwritten() -> None:
    with pytest.raises(ValueError, match="duplicate_json"):
        streaming.listing(b'[{"Path":"x","Path":"y","Size":3,"IsDir":false}]', EXPECTED)


async def test_actual_partial_process_exit_cannot_be_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processes: list[asyncio.subprocess.Process] = []

    async def start(
        _plan: Plan, _descriptor: int, _args: tuple[str, ...]
    ) -> asyncio.subprocess.Process:
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-B",
            "-c",
            "import sys;sys.stdout.write('a'*64+'  database/source.dump\\n');sys.exit(5)",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        processes.append(child)
        return child

    monkeypatch.setattr(streaming, "start", start)
    plan = Plan(
        tmp_path,
        "a" * 64,
        Path(sys.executable),
        "b" * 64,
        "synthetic-generation",
        "synthetic-escrow",
        3758096384,
        Retention(14, 8, 12),
    )
    with pytest.raises(streaming.ReadbackError, match="hash_command_failed"):
        await streaming.remote_hashes(plan, 0, (), EXPECTED)
    assert all(child.returncode is not None for child in processes)
