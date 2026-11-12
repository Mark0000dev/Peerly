"""Actual worker composition from main-owned resources; no app/settings/entrypoint here."""

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from opentelemetry.metrics import Meter
from opentelemetry.trace import Tracer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.ai.worker import ExecuteNextJob
from studymate.application.errors import StorageUnavailableError
from studymate.application.media.storage import MediaStorage
from studymate.domain.ai.jobs import Versions
from studymate.domain.ai.tasks import AiResult, AiTask, TriageReport
from studymate.infrastructure.ai.credentials import DedicatedCredentialCache
from studymate.infrastructure.ai.photos import RetainedDisplayReader
from studymate.infrastructure.ai.process import (
    CodexProcessExecutor,
    CredentialStateUncertainError,
    ProcessConfiguration,
    TerminationUncertainError,
)
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
from studymate.infrastructure.ai.runtime.diagnostics import (
    AiRuntimeCode,
    AiRuntimeDiagnostic,
    AiRuntimePhase,
)
from studymate.infrastructure.ai.runtime.health import (
    REPORT_GUARD_VERSION,
    RuntimeOwnershipError,
    SqlRuntimeHealth,
)
from studymate.infrastructure.ai.runtime.launch import PinnedProcessPolicy
from studymate.infrastructure.ai.runtime.policy import DEFAULT_MAX_PROCESSES, require_max_processes
from studymate.infrastructure.ai.runtime.preflight import PinnedCli
from studymate.infrastructure.ai.runtime.supervisor import AiWorkerSupervisor
from studymate.infrastructure.ai.sandbox import LinuxSandbox
from studymate.infrastructure.ai.telemetry import AiQueueSignals, ObservedAiQueue, ObservedAiStep

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine

    from studymate.infrastructure.ai.queue import TrustedReportSource


def _record_failure(phase: AiRuntimePhase, error: BaseException, *, primary: bool) -> None:
    categories: tuple[tuple[type[BaseException], AiRuntimeCode], ...] = (
        (StorageUnavailableError, AiRuntimeCode.STORAGE_UNAVAILABLE),
        (RuntimeOwnershipError, AiRuntimeCode.OWNERSHIP_LOST),
        (RuntimeAcceptanceError, AiRuntimeCode.RECEIPT_REJECTED),
        (TerminationUncertainError, AiRuntimeCode.PHYSICAL_STOP_UNCERTAIN),
        (CredentialStateUncertainError, AiRuntimeCode.CREDENTIAL_UNCERTAIN),
        (asyncio.CancelledError, AiRuntimeCode.CANCELLED),
    )
    code = next(
        (code for kind, code in categories if isinstance(error, kind)), AiRuntimeCode.UNEXPECTED
    )
    logging.getLogger(__name__).error(
        "ai_runtime_failure",
        extra={
            "event": "ai_runtime_failure",
            "ai_runtime_diagnostic": AiRuntimeDiagnostic(phase, code, primary),
        },
    )


async def _diagnosed[T](
    phase: AiRuntimePhase,
    operation: "Awaitable[T]",
    *,
    primary: bool = True,
    quiesce: asyncio.Event | None = None,
) -> T:
    try:
        return await operation
    except BaseException as error:
        # Normal shutdown cancellation must not masquerade as a primary failure.
        if not (
            isinstance(error, asyncio.CancelledError) and quiesce is not None and quiesce.is_set()
        ):
            _record_failure(phase, error, primary=primary)
        raise


async def _stop_sampling(task: asyncio.Task[None] | None) -> None:
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


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
    max_processes: int = DEFAULT_MAX_PROCESSES

    def __post_init__(self) -> None:
        require_max_processes(self.max_processes)
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
    signals: AiQueueSignals | None = None
    _active: bool = field(default=False, init=False, repr=False)

    async def _renew(self, quiesce: asyncio.Event) -> None:
        while not quiesce.is_set():
            try:
                await asyncio.wait_for(quiesce.wait(), RUNTIME_HEARTBEAT_SECONDS)
            except TimeoutError:
                await _diagnosed(
                    AiRuntimePhase.RECEIPT_RECHECK,
                    validate_runtime_receipt(
                        self.configuration.acceptance_artifact,
                        self.cli,
                        self.configuration.workspaces_root,
                        expectation=ReceiptExpectation(
                            model=self.configuration.model,
                            account_binding_sha256=self.binding_digest,
                            max_processes=self.configuration.max_processes,
                        ),
                    ),
                    quiesce=quiesce,
                )
                await _diagnosed(AiRuntimePhase.HEARTBEAT, self.health.heartbeat(), quiesce=quiesce)

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
                        max_processes=self.configuration.max_processes,
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

    async def _serve(
        self, stop: asyncio.Event, quiesce: asyncio.Event, tasks: list[asyncio.Task[None]]
    ) -> None:
        sampling: asyncio.Task[None] | None = None
        worker = asyncio.create_task(self.supervisor.run(quiesce))
        heartbeat = asyncio.create_task(self._renew(quiesce))

        async def await_stop() -> None:
            await stop.wait()

        stopping = asyncio.create_task(await_stop())
        tasks.extend((worker, heartbeat, stopping))
        if self.signals is not None:
            sampling = asyncio.create_task(self.signals.run(self.queue, quiesce))
            tasks.append(sampling)
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if stopping not in done:
                if worker in done:
                    await _diagnosed(AiRuntimePhase.PHYSICAL_CLEANUP, worker)
                elif heartbeat in done:
                    await heartbeat
                elif sampling is not None:
                    # Expected storage outages stay inside the sampler. Unexpected
                    # programming errors retain the usual fail-closed runtime lifecycle.
                    await sampling
                raise RuntimeOwnershipError("Worker or durable heartbeat stopped unexpectedly")
        finally:
            await _stop_sampling(sampling)
        quiesce.set()
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        # Stop new admissions before waiting for physical child/cache cleanup.
        await _diagnosed(AiRuntimePhase.REVOKE, self.health.revoke(clean=False))
        await _diagnosed(AiRuntimePhase.PHYSICAL_CLEANUP, worker)
        await _diagnosed(
            AiRuntimePhase.PHYSICAL_CLEANUP, self.health.recover_current_stopped(self.queue)
        )
        await _diagnosed(AiRuntimePhase.RETIRE, self.health.revoke(clean=True))

    async def run(self, stop: asyncio.Event) -> None:
        if self._active:
            raise RuntimeOwnershipError("Runtime is already active")
        self._active = True
        registered = False
        tasks: list[asyncio.Task[None]] = []
        quiesce = asyncio.Event()
        primary_error: BaseException | None = None
        try:
            await self.cli.verify()
            # Actual credentials are never read before operator proof/live deployment checks.
            if not await _diagnosed(AiRuntimePhase.RECEIPT_RECHECK, self._await_receipt(stop)):
                return
            await self.cache.validate_ready()
            await self.health.register()
            registered = True
            await _diagnosed(AiRuntimePhase.HEARTBEAT, self.health.heartbeat(ready=True))
            await self._serve(stop, quiesce, tasks)
            registered = False
        except BaseException as error:
            primary_error = error
            raise
        finally:
            quiesce.set()
            try:
                if registered:
                    await _diagnosed(
                        AiRuntimePhase.REVOKE, self.health.revoke(clean=False), primary=False
                    )
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
                results = await asyncio.gather(*tasks, return_exceptions=True)
                if results:
                    worker_result = results[0]
                    if (
                        isinstance(worker_result, BaseException)
                        and not isinstance(worker_result, asyncio.CancelledError)
                        and worker_result is not primary_error
                    ):
                        _record_failure(
                            AiRuntimePhase.PHYSICAL_CLEANUP, worker_result, primary=False
                        )
                self._active = False


def create_ai_worker_runtime(  # noqa: PLR0913 - explicit composition resources/ports, no option bag.
    sessions: async_sessionmaker[AsyncSession],
    storage: MediaStorage,
    configuration: AiRuntimeConfiguration,
    *,
    tracer: Tracer | None = None,
    meter: Meter | None = None,
    reports: "TrustedReportSource | None" = None,
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
                configuration.bubblewrap,
                configuration.prlimit,
                processes=configuration.max_processes,
                network_egress_restricted=True,
            ),
        ),
        cache,
        RetainedDisplayReader(storage),
        PinnedProcessPolicy(cli, configuration.max_processes),
    )
    worker_id = uuid4()
    queue = SqlAiQueue(sessions, reports=reports, worker_id=worker_id)
    health = SqlRuntimeHealth(
        sessions,
        worker_id,
        Versions(configuration.model),
        report_guard_version=REPORT_GUARD_VERSION if reports is not None else None,
    )
    step: Callable[[], Coroutine[object, object, bool]] = ExecuteNextJob(queue, executor)
    if tracer is not None or meter is not None:
        step = ObservedAiStep(ExecuteNextJob(ObservedAiQueue(queue), executor), tracer, meter)
    signals = AiQueueSignals(meter) if meter is not None else None
    return AiWorkerRuntime(
        configuration,
        cli,
        cache,
        queue,
        AiWorkerSupervisor(step),
        health,
        worker_id,
        credential_binding_digest(codec),
        signals,
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
                max_processes=self.configuration.max_processes,
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
                configuration.bubblewrap,
                configuration.prlimit,
                processes=configuration.max_processes,
                network_egress_restricted=True,
            ),
        ),
        cache,
        RetainedDisplayReader(storage),
        PinnedProcessPolicy(cli, configuration.max_processes),
    )
    return AiValidationRuntime(
        configuration, cli, cache, executor, credential_binding_digest(codec)
    )
