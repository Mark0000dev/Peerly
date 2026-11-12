"""One durable worker identity on the existing slot; expiry never authorizes takeover."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.ai.ports import AiUnavailableError
from studymate.domain.ai.jobs import Versions
from studymate.infrastructure.ai.persistence import SqlAiTransaction, lock_slot
from studymate.infrastructure.ai.runtime.availability import RUNTIME_TTL
from studymate.infrastructure.persistence.transactions import open_transaction

if TYPE_CHECKING:
    from studymate.infrastructure.ai.queue import SqlAiQueue


REPORT_GUARD_VERSION = 1


class RuntimeOwnershipError(Exception):
    """A predecessor or uncertain physical execution requires external recovery."""


@dataclass(frozen=True, slots=True)
class SqlRuntimeHealth:
    sessions: async_sessionmaker[AsyncSession]
    worker_id: UUID
    versions: Versions
    report_guard_version: int | None = None

    def __post_init__(self) -> None:
        if self.report_guard_version is not None and (
            type(self.report_guard_version) is not int
            or self.report_guard_version != REPORT_GUARD_VERSION
        ):
            raise ValueError("Report guard capability must be absent or version1")

    async def register(self) -> None:
        async with open_transaction(self.sessions) as session:
            slot = await lock_slot(session)
            if (
                slot.runtime_worker_id is not None
                or slot.runtime_state != "stopped"
                or slot.token is not None
            ):
                raise RuntimeOwnershipError(
                    "Previous runtime must be physically stopped and retired"
                )
            at = await SqlAiTransaction(session).now()
            slot.runtime_worker_id = self.worker_id
            slot.runtime_state = "starting"
            slot.runtime_started_at = at
            slot.runtime_heartbeat_at = at
            slot.runtime_valid_until = at + RUNTIME_TTL
            slot.runtime_model = self.versions.model
            slot.runtime_prompt = self.versions.prompt
            slot.runtime_schema = self.versions.schema
            slot.runtime_adapter = self.versions.adapter
            slot.runtime_report_guard_version = self.report_guard_version

    async def heartbeat(self, *, ready: bool = False) -> None:
        async with open_transaction(self.sessions) as session:
            slot = await lock_slot(session)
            at = await SqlAiTransaction(session).now()
            if (
                slot.runtime_worker_id != self.worker_id
                or slot.runtime_state not in {"starting", "ready"}
                or slot.runtime_valid_until is None
                or at >= slot.runtime_valid_until
                or slot.runtime_started_at is None
                or at < slot.runtime_started_at
            ):
                raise RuntimeOwnershipError("Runtime ownership or freshness lost")
            if ready and (slot.circuit is not None or slot.token is not None):
                raise AiUnavailableError
            slot.runtime_heartbeat_at = at
            slot.runtime_valid_until = at + RUNTIME_TTL
            if ready:
                slot.runtime_state = "ready"

    async def recover_current_stopped(self, queue: "SqlAiQueue") -> None:
        # Called ONLY after this supervisor returned with physical/cache cleanup complete.
        # Never used for a crashed predecessor, an expired lease, or a blocked supervisor.
        async with open_transaction(self.sessions) as session:
            slot = await lock_slot(session)
            if slot.runtime_worker_id != self.worker_id:
                raise RuntimeOwnershipError("Runtime owner changed during clean stop")
            token, generation = slot.token, slot.generation
        if token is not None:
            await queue.recover_stopped(token, generation, stopped=True)

    async def revoke(self, *, clean: bool) -> None:
        async with open_transaction(self.sessions) as session:
            slot = await lock_slot(session)
            if slot.runtime_worker_id != self.worker_id:
                raise RuntimeOwnershipError("Runtime owner changed")
            # Occupied SQL execution capacity is never inferred physically free here.
            if not clean or slot.token is not None:
                slot.runtime_state = "blocked"
                return
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
