"""Private parent-controlled predecessor recovery; no HTTP or expiry-based authority."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from studymate.infrastructure.ai.persistence import lock_slot
from studymate.infrastructure.ai.process import CredentialStateUncertainError
from studymate.infrastructure.ai.runtime.acceptance import (
    ReceiptExpectation,
    RuntimeReceipt,
    validate_runtime_receipt,
)
from studymate.infrastructure.ai.runtime.health import RuntimeOwnershipError
from studymate.infrastructure.persistence.transactions import open_transaction

if TYPE_CHECKING:
    from studymate.infrastructure.ai.runtime.factory import AiWorkerRuntime


SHA256_LENGTH = 64


@dataclass(frozen=True, slots=True)
class StoppedPredecessorEvidence:
    """Trusted supervisor attestation, NOT student input or self-verified process absence.

    Parent must stop the whole previous container/cgroup and preserve its auth/job
    volumes first. Digests reference private retained evidence, never credentials.
    """

    deployment_id: UUID
    worker_id: UUID
    token: UUID | None
    generation: int
    confirmed_at: datetime
    physical_stop_sha256: str
    cache_handoff_sha256: str

    def validate(self, receipt: RuntimeReceipt) -> None:
        at = datetime.now(UTC)
        if (
            self.deployment_id != receipt.deployment_id
            or self.confirmed_at.tzinfo is None
            or not at - timedelta(minutes=15) <= self.confirmed_at <= at
            or self.generation < 0
            or any(
                len(digest) != SHA256_LENGTH or any(c not in "0123456789abcdef" for c in digest)
                for digest in (self.physical_stop_sha256, self.cache_handoff_sha256)
            )
        ):
            raise RuntimeOwnershipError("Invalid predecessor recovery attestation")


async def recover_stopped_predecessor(
    runtime: "AiWorkerRuntime",
    evidence: StoppedPredecessorEvidence,
) -> None:
    """Validate the current deployment receipt before touching recovery state.

    This is an operator-local trusted Python boundary, never an automatic restart
    hook. Failed cache recovery leaves the predecessor durably blocked. Circuit
    state is preserved; resolving authentication failures is a separate decision.
    """
    receipt = await validate_runtime_receipt(
        runtime.configuration.acceptance_artifact,
        runtime.cli,
        runtime.configuration.workspaces_root,
        expectation=ReceiptExpectation(
            stage="containment",
            model=runtime.configuration.model,
            account_binding_sha256=runtime.binding_digest,
            max_processes=runtime.configuration.max_processes,
        ),
    )
    health, queue, cache = runtime.health, runtime.queue, runtime.cache
    evidence.validate(receipt)
    async with open_transaction(health.sessions) as session:
        slot = await lock_slot(session)
        if (slot.runtime_worker_id, slot.token, slot.generation) != (
            evidence.worker_id,
            evidence.token,
            evidence.generation,
        ):
            raise RuntimeOwnershipError("Predecessor recovery fence changed")
        slot.runtime_state = "blocked"
    try:
        await cache.validate_ready()
    except CredentialStateUncertainError:
        await cache.recover_stopped(confirmed_stopped=True)
        await cache.validate_ready()
    if evidence.token is not None:
        await queue.recover_stopped(
            evidence.token, evidence.generation, stopped=True, expected_worker=evidence.worker_id
        )
    async with open_transaction(health.sessions) as session:
        slot = await lock_slot(session)
        if (
            slot.runtime_worker_id != evidence.worker_id
            or slot.runtime_state != "blocked"
            or slot.token is not None
            or slot.generation != evidence.generation
        ):
            raise RuntimeOwnershipError("Predecessor retirement fence changed")
        slot.runtime_state = "stopped"
        slot.runtime_worker_id = None
        slot.runtime_started_at = None
        slot.runtime_heartbeat_at = None
        slot.runtime_valid_until = None
        slot.runtime_model = None
        slot.runtime_prompt = None
        slot.runtime_schema = None
        slot.runtime_adapter = None
        slot.runtime_report_guard_version = None
