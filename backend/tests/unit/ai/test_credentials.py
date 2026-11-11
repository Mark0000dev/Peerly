import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict, Unpack

import pytest
from pydantic import BaseModel, ConfigDict

from studymate.application.ai.ports import AiExecutorError
from studymate.domain.ai.jobs import Failure
from studymate.infrastructure.ai.credentials import (
    MAX_CREDENTIAL_BYTES,
    CredentialDocument,
    DedicatedCredentialCache,
)
from studymate.infrastructure.ai.process import (
    CredentialStateUncertainError,
    TerminationUncertainError,
)


class SyntheticDocument(BaseModel):
    """Deliberately NOT a claim about actual Codex cache fields or JWT identity."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    mode: Literal["synthetic-subscription"]
    account: str
    access: str
    refresh: str


@dataclass(frozen=True, slots=True)
class SyntheticCodec:
    def validate(self, encoded: bytes) -> CredentialDocument:
        parsed = SyntheticDocument.model_validate_json(encoded)
        return CredentialDocument(parsed.account, parsed.model_dump_json().encode())


def synthetic(generation: str, account: str = "synthetic-owner") -> bytes:
    return (
        SyntheticDocument(
            mode="synthetic-subscription",
            account=account,
            access="synthetic-access-" + generation,
            refresh="synthetic-refresh-" + generation,
        )
        .model_dump_json()
        .encode()
    )


async def private_file(path: Path, encoded: bytes) -> None:
    await asyncio.to_thread(path.write_bytes, encoded)
    await asyncio.to_thread(path.chmod, 0o600)


async def cache(tmp_path: Path) -> DedicatedCredentialCache:
    source = tmp_path / "credential-cache"
    jobs = tmp_path / "workspaces"
    for directory in (source, jobs):
        await asyncio.to_thread(directory.mkdir, mode=0o700)
    await private_file(source / "auth.json", synthetic("first"))
    return DedicatedCredentialCache(source, "synthetic-owner", SyntheticCodec(), jobs)


async def destination(state: DedicatedCredentialCache, name: str = "one") -> Path:
    parent = state.workspaces_root / ("peerly-ai-" + name)
    await asyncio.to_thread(parent.mkdir, mode=0o700)
    auth = parent / "auth"
    await asyncio.to_thread(auth.mkdir, mode=0o700)
    return auth


async def test_rotated_cache_survives_into_next_fresh_context_only_credentials_persist(
    tmp_path: Path,
) -> None:
    state = await cache(tmp_path)
    auth = await destination(state)
    async with state.lease(auth):
        assert await asyncio.to_thread((auth / "auth.json").read_bytes) == synthetic("first")
        assert (
            await asyncio.to_thread((auth / "auth.json").stat)
        ).st_mode & 0o777 == PRIVATE_FILE_MODE
        await private_file(auth / "auth.json", synthetic("rotated"))
        await asyncio.to_thread((auth / "private-history.json").write_text, "PRIVATE_JOB_HISTORY")
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic(
        "rotated"
    )
    assert not await asyncio.to_thread((auth / "auth.json").exists)
    assert sorted(
        path.name for path in await asyncio.to_thread(lambda: list(state.directory.iterdir()))
    ) == [".lock", "auth.json"]
    following = await destination(state, "two")
    async with state.lease(following):
        assert await asyncio.to_thread((following / "auth.json").read_bytes) == synthetic("rotated")
        assert not await asyncio.to_thread((following / "private-history.json").exists)


async def test_failure_still_checkpoints_same_account_normal_cli_refresh(tmp_path: Path) -> None:
    state = await cache(tmp_path)
    auth = await destination(state)

    async def failed_job() -> None:
        async with state.lease(auth):
            await private_file(auth / "auth.json", synthetic("rotated"))
            raise AiExecutorError(Failure.INVALID_OUTPUT)

    with pytest.raises(AiExecutorError) as failed:
        await failed_job()
    assert failed.value.failure == Failure.INVALID_OUTPUT
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic(
        "rotated"
    )


async def test_cancellation_after_confirmed_child_stop_preserves_updated_credentials(
    tmp_path: Path,
) -> None:
    state = await cache(tmp_path)
    auth = await destination(state)
    started = asyncio.Event()

    async def operation() -> None:
        async with state.lease(auth):
            await private_file(auth / "auth.json", synthetic("rotated"))
            started.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(operation())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic(
        "rotated"
    )


async def test_account_switch_or_private_history_cannot_replace_owner_cache(tmp_path: Path) -> None:
    state = await cache(tmp_path)
    auth = await destination(state)

    async def changed_account() -> None:
        async with state.lease(auth):
            await private_file(auth / "auth.json", synthetic("other", account="different-owner"))

    with pytest.raises(CredentialStateUncertainError):
        await changed_account()
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic("first")
    assert await asyncio.to_thread((state.directory / "active.json").exists)

    async def blocked() -> None:
        async with state.lease(await destination(state, "blocked")):
            raise AssertionError("Unfinished cache cannot seed another process")

    with pytest.raises(AiExecutorError) as failed:
        await blocked()
    assert failed.value.failure == Failure.AUTH
    await private_file(auth / "auth.json", synthetic("valid-rotated"))
    assert await state.recover_stopped(confirmed_stopped=True) == auth
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic(
        "valid-rotated"
    )


async def test_uncertain_stop_preserves_pending_cache_until_explicit_stopped_recovery(
    tmp_path: Path,
) -> None:
    state = await cache(tmp_path)
    auth = await destination(state)

    async def uncertain() -> None:
        async with state.lease(auth):
            await private_file(auth / "auth.json", synthetic("rotated"))
            raise TerminationUncertainError("Synthetic physical stop is unknown")

    with pytest.raises(TerminationUncertainError):
        await uncertain()
    with pytest.raises(TerminationUncertainError):
        await state.recover_stopped(confirmed_stopped=False)
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic("first")
    assert await asyncio.to_thread((auth / "auth.json").read_bytes) == synthetic("rotated")
    assert await state.recover_stopped(confirmed_stopped=True) == auth
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic(
        "rotated"
    )


@pytest.mark.parametrize(
    "corruption", ["empty", "oversized", "public", "symlink", "fifo", "unknown_fields", "api_mode"]
)
async def test_invalid_source_auth_fails_closed_without_secret_error_echo(
    tmp_path: Path, corruption: str
) -> None:
    state = await cache(tmp_path)
    source = state.directory / "auth.json"
    if corruption == "empty":
        await private_file(source, b"")
    elif corruption == "oversized":
        await private_file(source, b"x" * (MAX_CREDENTIAL_BYTES + 1))
    elif corruption == "public":
        await asyncio.to_thread(source.chmod, 0o644)
    elif corruption in {"symlink", "fifo"}:
        await asyncio.to_thread(source.unlink)
        if corruption == "symlink":
            await asyncio.to_thread(source.symlink_to, tmp_path / "never-read")
        else:
            await asyncio.to_thread(os.mkfifo, source, 0o600)
    elif corruption == "api_mode":
        await private_file(source, b'{"OPENAI_API_KEY":"PRIVATE_SENTINEL"}')
    else:
        payload = {
            "mode": "synthetic-subscription",
            "account": "synthetic-owner",
            "access": "synthetic-access",
            "refresh": "synthetic-refresh",
            "private_history": "PRIVATE_SENTINEL",
        }
        await private_file(source, json.dumps(payload).encode())

    async def stage() -> None:
        async with state.lease(await destination(state)):
            raise AssertionError("Invalid auth must never start transport")

    with pytest.raises(AiExecutorError) as failed:
        await stage()
    assert failed.value.failure == Failure.AUTH
    assert "PRIVATE_SENTINEL" not in str(failed.value)


async def test_parallel_auth_lease_and_uncoordinated_reseed_cannot_overwrite_new_cache(
    tmp_path: Path,
) -> None:
    state = await cache(tmp_path)
    first, second = await destination(state), await destination(state, "two")

    async def parallel() -> None:
        async with state.lease(second):
            raise AssertionError("Auth cache ownership is exclusive")

    async def reseeded() -> None:
        async with state.lease(first):
            with pytest.raises(AiExecutorError):
                await parallel()
            await private_file(first / "auth.json", synthetic("rotated"))
            await private_file(state.directory / "auth.json", synthetic("new-provisioned"))

    with pytest.raises(CredentialStateUncertainError):
        await reseeded()
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic(
        "new-provisioned"
    )


PRIVATE_FILE_MODE = 0o600


@pytest.mark.parametrize(
    "private_field", ["private_history", "prompt", "sessions", "config", "OPENAI_API_KEY"]
)
async def test_refreshed_cache_cannot_smuggle_job_history_config_or_api_keys(
    tmp_path: Path, private_field: str
) -> None:
    state = await cache(tmp_path)
    auth = await destination(state)

    async def corrupted_refresh() -> None:
        async with state.lease(auth):
            payload = {
                "mode": "synthetic-subscription",
                "account": "synthetic-owner",
                "access": "synthetic-next",
                "refresh": "synthetic-next",
                private_field: "PRIVATE_SENTINEL",
            }
            await private_file(auth / "auth.json", json.dumps(payload).encode())

    with pytest.raises(CredentialStateUncertainError) as blocked:
        await corrupted_refresh()
    assert "PRIVATE_SENTINEL" not in str(blocked.value)
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic("first")


async def test_refresh_atomic_replace_failure_leaves_original_and_recoverable_pending_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from studymate.infrastructure.ai import credentials

    state = await cache(tmp_path)
    auth = await destination(state)
    original = credentials._atomic

    def disk_full(directory: int, name: str, encoded: bytes) -> None:
        if name == "auth.json":
            raise OSError("PRIVATE_DISK_DETAIL")
        original(directory, name, encoded)

    monkeypatch.setattr(credentials, "_atomic", disk_full)

    async def rotated() -> None:
        async with state.lease(auth):
            await private_file(auth / "auth.json", synthetic("rotated"))

    with pytest.raises(CredentialStateUncertainError):
        await rotated()
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic("first")
    monkeypatch.setattr(credentials, "_atomic", original)
    await state.recover_stopped(confirmed_stopped=True)
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic(
        "rotated"
    )


async def test_recovery_recognizes_already_committed_refresh_without_restoring_old_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from studymate.infrastructure.ai import credentials

    state = await cache(tmp_path)
    auth = await destination(state)
    original = credentials._atomic

    def uncertain_fsync(directory: int, name: str, encoded: bytes) -> None:
        original(directory, name, encoded)
        if name == "auth.json":
            raise OSError("Synthetic crash after replace")

    monkeypatch.setattr(credentials, "_atomic", uncertain_fsync)

    async def rotated() -> None:
        async with state.lease(auth):
            await private_file(auth / "auth.json", synthetic("rotated"))

    with pytest.raises(CredentialStateUncertainError):
        await rotated()
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic(
        "rotated"
    )
    monkeypatch.setattr(credentials, "_atomic", original)
    await state.recover_stopped(confirmed_stopped=True)
    assert not await asyncio.to_thread((state.directory / "active.json").exists)


async def test_auth_target_cannot_be_reused_symlinked_or_outside_workspace(tmp_path: Path) -> None:
    state = await cache(tmp_path)
    auth = await destination(state)
    await private_file(auth / "auth.json", b"synthetic-existing")

    async def stage(target: Path) -> None:
        async with state.lease(target):
            raise AssertionError("Unsafe destination cannot be used")

    with pytest.raises(AiExecutorError):
        await stage(auth)
    assert await asyncio.to_thread((auth / "auth.json").read_bytes) == b"synthetic-existing"
    with pytest.raises(AiExecutorError):
        await stage(tmp_path / "unrelated")
    await asyncio.to_thread((auth / "auth.json").unlink)
    await asyncio.to_thread(auth.rmdir)
    await asyncio.to_thread(auth.symlink_to, state.directory, target_is_directory=True)
    with pytest.raises(AiExecutorError):
        await stage(auth)
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic("first")


async def test_private_cache_root_symlinks_and_home_fallback_are_rejected(tmp_path: Path) -> None:
    state = await cache(tmp_path)
    link = tmp_path / "cache-link"
    await asyncio.to_thread(link.symlink_to, state.directory, target_is_directory=True)

    async def stage(root: Path) -> None:
        candidate = DedicatedCredentialCache(
            root, "synthetic-owner", SyntheticCodec(), state.workspaces_root
        )
        async with candidate.lease(await destination(state, root.name)):
            raise AssertionError("Untrusted source root cannot be used")

    with pytest.raises(AiExecutorError):
        await stage(link)
    with pytest.raises(AiExecutorError):
        await stage(Path("/home/never-inspect"))
    with pytest.raises(ValueError, match="separate"):
        DedicatedCredentialCache(
            state.directory, "synthetic-owner", SyntheticCodec(), state.directory
        )


async def test_unknown_journal_never_turns_into_arbitrary_auth_file_read(tmp_path: Path) -> None:
    state = await cache(tmp_path)
    await private_file(
        state.directory / "active.json",
        b'{"destination":"/home/never-inspect","digest":"' + b"a" * 64 + b'"}',
    )
    with pytest.raises(CredentialStateUncertainError):
        await state.recover_stopped(confirmed_stopped=True)
    await private_file(state.directory / "active.json", b'{"invalid":"PRIVATE_SENTINEL"}')
    with pytest.raises(CredentialStateUncertainError) as blocked:
        await state.recover_stopped(confirmed_stopped=True)
    assert "PRIVATE_SENTINEL" not in str(blocked.value)


async def test_fake_process_refreshes_persistent_credentials_without_inheriting_other_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from studymate.infrastructure.ai.process import CodexProcessExecutor, ProcessConfiguration
    from tests.unit.ai.test_process import FakePhotos, executable, fake_policy, task

    state = await cache(tmp_path)
    marker = tmp_path / "invocations"
    body = (
        "auth=pathlib.Path(os.environ['CODEX_HOME'])/'auth.json'\n"
        "cached=json.loads(auth.read_text())\n"
        f"counter=pathlib.Path({str(marker)!r})\n"
        "number=int(counter.read_text()) if counter.exists() else 0\n"
        "assert cached['account']=='synthetic-owner'\n"
        "expected='synthetic-access-first' if number==0 else 'synthetic-access-rotated'\n"
        "assert cached['access']==expected\n"
        "cached['access']='synthetic-access-rotated'\n"
        "cached['refresh']='synthetic-refresh-rotated'\n"
        "auth.write_text(json.dumps(cached))\n"
        "counter.write_text(str(number+1))\n"
        "assert 'forced_login_method=\"chatgpt\"' in sys.argv\n"
        "assert 'cli_auth_credentials_store=\"file\"' in sys.argv\n"
        "assert 'features.apps=false' in sys.argv\n"
        "assert 'features.multi_agent=false' in sys.argv\n"
        "assert 'features.view_image=false' in sys.argv\n"
        "for key in os.environ:\n"
        " assert not key.endswith('API_KEY') and not key.startswith('AWS_')\n"
        " assert key!='MCP_SERVER_TOKEN'\n"
        'result.write_text(\'{"suggestion":"Editable synthetic"}\')'
    )
    for key in (
        "OPENAI_API_KEY",
        "CODEX_API_KEY",
        "ANTHROPIC_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "MCP_SERVER_TOKEN",
    ):
        monkeypatch.setenv(key, "SYNTHETIC_SECRET_ONLY")
    configuration = ProcessConfiguration(
        await executable(tmp_path, body),
        "synthetic-cli 1",
        "synthetic-model",
        state.workspaces_root,
    )
    executor = CodexProcessExecutor(
        configuration, state, FakePhotos(), await fake_policy(configuration.executable)
    )
    await executor.execute(task(), 2)
    await executor.execute(task(), 2)
    assert await asyncio.to_thread(marker.read_text) == "2"
    assert not list(state.workspaces_root.iterdir())
    assert sorted(path.name for path in state.directory.iterdir()) == [".lock", "auth.json"]


@pytest.mark.parametrize("encoded", [b"", b"x" * (MAX_CREDENTIAL_BYTES + 1)])
def test_credential_document_itself_is_bounded_and_repr_private(encoded: bytes) -> None:
    with pytest.raises(ValueError, match="Bounded"):
        CredentialDocument("synthetic-owner", encoded)
    assert "synthetic-owner" not in repr(CredentialDocument("synthetic-owner", synthetic("first")))


async def test_repeated_cancel_during_staging_finishes_file_io_and_releases_cache_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from studymate.infrastructure.ai.credentials import _Lease

    state = await cache(tmp_path)
    auth = await destination(state)
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original = DedicatedCredentialCache._stage

    def paused_stage(self: DedicatedCredentialCache, target: Path) -> _Lease:
        result = original(self, target)
        loop.call_soon_threadsafe(started.set)
        assert release.wait(3)
        return result

    monkeypatch.setattr(DedicatedCredentialCache, "_stage", paused_stage)

    async def operation() -> None:
        async with state.lease(auth):
            raise AssertionError("Cancelled staging must not run inference")

    task = asyncio.create_task(operation())
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not await asyncio.to_thread((auth / "auth.json").exists)
    assert not await asyncio.to_thread((state.directory / "active.json").exists)
    monkeypatch.setattr(DedicatedCredentialCache, "_stage", original)
    async with state.lease(await destination(state, "next")):
        pass


async def test_unknown_process_stop_retains_auth_handoff_until_kernel_stop_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from studymate.infrastructure.ai import process
    from studymate.infrastructure.ai.process import CodexProcessExecutor, ProcessConfiguration
    from tests.unit.ai.test_process import FakePhotos, executable, fake_policy, task

    state = await cache(tmp_path)
    body = (
        "auth=pathlib.Path(os.environ['CODEX_HOME'])/'auth.json'\n"
        "cached=json.loads(auth.read_text()); cached['access']='synthetic-access-rotated'\n"
        "cached['refresh']='synthetic-refresh-rotated'; auth.write_text(json.dumps(cached))\n"
        'result.write_text(\'{"suggestion":"Editable synthetic"}\')'
    )
    configuration = ProcessConfiguration(
        await executable(tmp_path, body),
        "synthetic-cli 1",
        "synthetic-model",
        state.workspaces_root,
    )
    executor = CodexProcessExecutor(
        configuration, state, FakePhotos(), await fake_policy(configuration.executable)
    )
    stops = 0

    def uncertain_after_probe(pid: int) -> bool:
        nonlocal stops
        assert pid > 0
        stops += 1
        return stops > 1

    monkeypatch.setattr(process, "_group_exists", uncertain_after_probe)
    with pytest.raises(TerminationUncertainError):
        await executor.execute(task(), 2)
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic("first")
    assert list(state.workspaces_root.iterdir())
    recovered = await state.recover_stopped(confirmed_stopped=True)
    assert await asyncio.to_thread((state.directory / "auth.json").read_bytes) == synthetic(
        "rotated"
    )
    await asyncio.to_thread(shutil.rmtree, recovered.parent)
    assert not list(state.workspaces_root.iterdir())


async def test_cancel_during_os_spawn_reaps_child_before_auth_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from studymate.infrastructure.ai.process import CodexProcessExecutor, ProcessConfiguration
    from tests.unit.ai.test_process import FakePhotos, executable, fake_policy, task

    state = await cache(tmp_path)
    started, release = asyncio.Event(), asyncio.Event()
    children: list[asyncio.subprocess.Process] = []
    original = asyncio.create_subprocess_exec

    class SpawnOptions(TypedDict):
        stdin: int
        stdout: int
        stderr: int
        cwd: Path
        start_new_session: bool
        close_fds: bool
        env: dict[str, str]
        limit: int

    async def slow_handoff(
        *arguments: str, **options: Unpack[SpawnOptions]
    ) -> asyncio.subprocess.Process:
        child = await original(*arguments, **options)
        if "--version" not in arguments:
            children.append(child)
            started.set()
            await release.wait()
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", slow_handoff)
    binary = await executable(tmp_path, "time.sleep(20)")
    executor = CodexProcessExecutor(
        ProcessConfiguration(
            binary,
            "synthetic-cli 1",
            "synthetic-model",
            state.workspaces_root,
        ),
        state,
        FakePhotos(),
        await fake_policy(binary),
    )
    operation = asyncio.create_task(executor.execute(task(), 2))
    await started.wait()
    operation.cancel()
    await asyncio.sleep(0)
    operation.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert children
    assert children[0].returncode is not None
    assert not await asyncio.to_thread((state.directory / "active.json").exists)
    assert not list(state.workspaces_root.iterdir())
