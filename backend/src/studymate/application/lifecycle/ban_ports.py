"""Actual ban transaction boundary; main owns account-lock ordering and SQL effects."""

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.lifecycle.intents import LifecycleIntent
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.lifecycle.states import AccountLifecycle, BanTransition, LifecycleOperation


class LifecycleTargetUnavailableError(Exception):
    """No actual requested account; HTTP mapping is main-owned and not published here."""


class BanTransaction(OperatorAuditTransaction, Protocol):
    async def target_lifecycle(self, account_id: UUID) -> AccountLifecycle | None: ...

    async def prior_lifecycle_intent(
        self,
        actor_id: UUID,
        operation: LifecycleOperation,
        key: IntentKey,
    ) -> LifecycleIntent | None: ...

    async def apply_ban_transition(self, transition: BanTransition) -> None:
        """Actual changed flag+immutable source+pending closure+canonical, SAME transaction.

        Reuse affected-account request/finality helper with no lower peer account locks.
        Preserve deletion, accepted conversations and all accumulated business history.
        No-op/replayed intents never call this port. No invented inspection audit source.
        """
        ...

    async def remember_lifecycle_intent(self, intent: LifecycleIntent, at: datetime) -> None: ...


class BanUnitOfWork(Protocol):
    def transaction(
        self,
        actor_secret_digest: bytes,
        target_account_id: UUID,
    ) -> AbstractAsyncContextManager[BanTransaction]:
        """Resolve real actor, SORT actor/target account locks BEFORE session/current grant.

        All source/effect/intent changes roll back on cancellation/final expiry/commit error.
        No new actor authority is inferred by resolving the digest for lock ordering.
        """
        ...
