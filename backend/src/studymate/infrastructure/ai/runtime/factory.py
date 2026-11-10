"""Actual worker composition from main-owned resources; no app/settings/entrypoint here."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.ai.worker import ExecuteNextJob
from studymate.application.media.storage import MediaStorage
from studymate.domain.ai.jobs import Versions
from studymate.domain.ai.tasks import AiResult, AiTask, TriageReport
from studymate.infrastructure.ai.credentials import DedicatedCredentialCache
from studymate.infrastructure.ai.photos import RetainedDisplayReader
from studymate.infrastructure.ai.process import CodexProcessExecutor, ProcessConfiguration
from studymate.infrastructure.ai.queue import SqlAiQueue
from studymate.infrastructure.ai.runtime.acceptance import (
    ReceiptExpectation,
    RuntimeAcceptanceError,
    RuntimeReceiptPendingError,
    validate_runtime_receipt,
)
from studymate.infrastructure.ai.runtime.availability import RUNTIME_HEARTBEAT_SECONDS
from studymate.infrastructure.ai.runtime.credential_codec import (
    Codex167CredentialCodec,
    credential_binding_digest,
)
from studymate.infrastructure.ai.runtime.health import RuntimeOwnershipError, SqlRuntimeHealth
from studymate.infrastructure.ai.runtime.launch import PinnedProcessPolicy
from studymate.infrastructure.ai.runtime.preflight import PinnedCli
from studymate.infrastructure.ai.runtime.supervisor import AiWorkerSupervisor
from studymate.infrastructure.ai.sandbox import LinuxSandbox


@dataclass(frozen=True, slots=True)
class AiRuntimeConfiguration:
    executable: Path
    expected_version: str
    expected_sha256: str
    model: str
    credential_directory: Path = field(repr=False)
    expected_account: str = field(repr=False)
    expected_login_owner: str = field(repr=False)
    expected_oauth_issuer: str = field(repr=False)
    expected_oauth_client_id: str = field(repr=False)
    workspaces_root: Path
    bubblewrap: Path
    prlimit: Path
    acceptance_artifact: Path

    def __post_init__(self) -> None:
        Versions(self.model)
        for path in (self.credential_directory, self.workspaces_root, self.acceptance_artifact):
            if (
                not path.is_absolute()
                or ".." in path.parts
                or any(path.is_relative_to(root) for root in ("/home", "/root"))
            ):
                raise ValueError("Dedicated non-home runtime paths required")
        if (
            self.credential_directory.is_relative_to(self.workspaces_root)
            or self.workspaces_root.is_relative_to(self.credential_directory)
            or self.acceptance_artifact.is_relative_to(self.workspaces_root)
            or self.acceptance_artifact.is_relative_to(self.credential_directory)
        ):
            raise ValueError("Persistent credentials must be outside job storage")


@dataclass(slots=True)
class AiWorkerRuntime:
    configuration: AiRuntimeConfiguration
    cli: PinnedCli
    cache: DedicatedCredentialCache
    queue: SqlAiQueue
    supervisor: AiWorkerSupervisor
    health: SqlRuntimeHealth
    worker_id: UUID
    binding_digest: str
    _active: bool = field(default=False, init=False, repr=False)

    async def _renew(self, quiesce: asyncio.Event) -> None:
        while not quiesce.is_set():
            try:
                await asyncio.wait_for(quiesce.wait(), RUNTIME_HEARTBEAT_SECONDS)
            except TimeoutError:
                await validate_runtime_receipt(
                    self.configuration.acceptance_artifact,
                    self.cli,
                    self.configuration.workspaces_root,
                    expectation=ReceiptExpectation(
                        model=self.configuration.model, account_binding_sha256=self.binding_digest
                    ),
                )
                await self.health.heartbeat()

    async def _await_receipt(self, stop: asyncio.Event) -> bool:
        # Preserve namespaces while parent installs proof, without reading credentials.
        deadline = asyncio.get_running_loop().time() + 900
        while not stop.is_set():
            try:
                await validate_runtime_receipt(
                    self.configuration.acceptance_artifact,
                    self.cli,
                    self.configuration.workspaces_root,
                    expectation=ReceiptExpectation(
                        model=self.configuration.model,
                        account_binding_sha256=self.binding_digest,
                    ),
                )
                return True
            except RuntimeReceiptPendingError:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise RuntimeAcceptanceError("runtime_proof_wait_expired") from None
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), min(1.0, remaining))
        return False

    async def run(self, stop: asyncio.Event) -> None:
        if self._active:
            raise RuntimeOwnershipError("Runtime is already active")
        self._active = True
        registered = False
        tasks: list[asyncio.Task[None]] = []
        quiesce = asyncio.Event()
        try:
            await self.cli.verify()
            # Actual credentials are never read before operator proof/live deployment checks.
            if not await self._await_receipt(stop):
                return
            await self.cache.validate_ready()
            await self.health.register()
            registered = True
            await self.health.heartbeat(ready=True)
            worker = asyncio.create_task(self.supervisor.run(quiesce))
            heartbeat = asyncio.create_task(self._renew(quiesce))

            async def await_stop() -> None:
                await stop.wait()

            stopping = asyncio.create_task(await_stop())
            tasks.extend((worker, heartbeat, stopping))
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if stopping not in done:
                if worker in done:
                    await worker
                else:
                    await heartbeat
                raise RuntimeOwnershipError("Worker or durable heartbeat stopped unexpectedly")
            quiesce.set()
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            # Stop new admissions before waiting for physical child/cache cleanup.
            await self.health.revoke(clean=False)
            await worker
            await self.health.recover_current_stopped(self.queue)
            await self.health.revoke(clean=True)
            registered = False
        finally:
            quiesce.set()
            try:
                if registered:
                    await self.health.revoke(clean=False)
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                self._active = False


def create_ai_worker_runtime(
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    configuration: AiRuntimeConfiguration,
) -> AiWorkerRuntime:
    """Main supplies dedicated pool1/overflow0 and owns engine/storage disposal."""
    cli = PinnedCli(
        configuration.executable, configuration.expected_version, configuration.expected_sha256
    )
    codec = Codex167CredentialCodec(
        configuration.expected_account,
        configuration.expected_login_owner,
        configuration.expected_oauth_issuer,
        configuration.expected_oauth_client_id,
    )
    cache = DedicatedCredentialCache(
        configuration.credential_directory,
        configuration.expected_account,
        codec,
        configuration.workspaces_root,
    )
    executor = CodexProcessExecutor(
        ProcessConfiguration(
            configuration.executable,
            configuration.expected_version,
            configuration.model,
            configuration.workspaces_root,
            sandbox=LinuxSandbox(
                configuration.bubblewrap, configuration.prlimit, network_egress_restricted=True
            ),
        ),
        cache,
        RetainedDisplayReader(storage),
        PinnedProcessPolicy(cli),
    )
    worker_id = uuid4()
    queue = SqlAiQueue(sessions, worker_id=worker_id)
    health = SqlRuntimeHealth(sessions, worker_id, Versions(configuration.model))
    return AiWorkerRuntime(
        configuration,
        cli,
        cache,
        queue,
        AiWorkerSupervisor(ExecuteNextJob(queue, executor)),
        health,
        worker_id,
        credential_binding_digest(codec),
    )


@dataclass(frozen=True, slots=True)
class AiValidationRuntime:
    """Private parent-controlled Stage2, with no database readiness/admission authority."""

    configuration: AiRuntimeConfiguration
    cli: PinnedCli
    cache: DedicatedCredentialCache
    executor: CodexProcessExecutor
    binding_digest: str

    async def execute(self, task: "AiTask", budget_seconds: float) -> "AiResult":
        if isinstance(task, TriageReport):
            raise ValueError("Validation flow does not grant report triage authority")
        await self.cli.verify()
        receipt = await validate_runtime_receipt(
            self.configuration.acceptance_artifact,
            self.cli,
            self.configuration.workspaces_root,
            expectation=ReceiptExpectation(
                stage="containment",
                model=self.configuration.model,
                account_binding_sha256=self.binding_digest,
            ),
        )
        if receipt.stage != "containment":
            raise RuntimeAcceptanceError("validation_requires_containment_stage")
        await self.cache.validate_ready()
        return await self.executor.execute(task, budget_seconds)


def create_ai_validation_runtime(
    storage: MediaStorage, configuration: AiRuntimeConfiguration
) -> AiValidationRuntime:
    cli = PinnedCli(
        configuration.executable, configuration.expected_version, configuration.expected_sha256
    )
    codec = Codex167CredentialCodec(
        configuration.expected_account,
        configuration.expected_login_owner,
        configuration.expected_oauth_issuer,
        configuration.expected_oauth_client_id,
    )
    cache = DedicatedCredentialCache(
        configuration.credential_directory,
        configuration.expected_account,
        codec,
        configuration.workspaces_root,
    )
    executor = CodexProcessExecutor(
        ProcessConfiguration(
            configuration.executable,
            configuration.expected_version,
            configuration.model,
            configuration.workspaces_root,
            sandbox=LinuxSandbox(
                configuration.bubblewrap, configuration.prlimit, network_egress_restricted=True
            ),
        ),
        cache,
        RetainedDisplayReader(storage),
        PinnedProcessPolicy(cli),
    )
    return AiValidationRuntime(
        configuration, cli, cache, executor, credential_binding_digest(codec)
    )
