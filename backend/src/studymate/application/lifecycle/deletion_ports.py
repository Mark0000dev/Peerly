"""Main-owned deletion proof/transaction boundary, with no cookie or recent-auth policy."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentityTransaction
from studymate.application.lifecycle.intents import LifecycleIntent
from studymate.domain.lifecycle.states import (
    AccountLifecycle,
    DeletionTransition,
    LifecycleOperation,
)
from studymate.domain.time import require_aware


class DeletionWorkflowUnavailableError(Exception):
    """Owned proof unavailable/expired; no public recovery/HTTP mapping specified here."""


@dataclass(frozen=True, slots=True)
class DeletionWorkflowAuthorization:
    id: UUID
    account_id: UUID
    session_id: UUID
    expires_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.expires_at)

    def is_valid(self, at: datetime) -> bool:
        require_aware(at)
        return at < self.expires_at


class DeletionTransaction(IdentityTransaction, Protocol):
    async def authorized_deletion_workflow(
        self,
        session_digest: bytes,
        workflow_id: UUID,
    ) -> DeletionWorkflowAuthorization | None:
        """Actual locked proof checked by main, NEVER authority from a public workflow UUID.

        The command proof is the actual opaque ORIGINAL session credential digest plus
        its workflow/session binding; no ambient cookie/proof argument is implied here.
        Main owns actual preflight/recent Google authorization and secret/proof cleanup.
        Original revoked session can access ONLY its owned committed workflow receipt.
        Separate post-cookie-clear status capability belongs to main status/preflight,
        with an explicit proof port; a workflow UUID alone grants nothing.
        """
        ...

    async def target_lifecycle(self, account_id: UUID) -> AccountLifecycle | None: ...

    async def prior_lifecycle_intent(
        self,
        actor_id: UUID,
        operation: LifecycleOperation,
        key: IntentKey,
    ) -> LifecycleIntent | None: ...

    async def apply_deletion_transition(self, transition: DeletionTransition) -> None:
        """SAME TX actual source+flag+all owned invalidations+closure+canonical, retain history.

        All sessions, verification/delivery and attributable login work are invalidated;
        never assign unbound login ownership or claim recall of in-flight external work.
        Use actual request finality/pair helpers. All business/media/identity uniqueness,
        role, analytics and audit history remain; no restore/recreation/purge.
        """
        ...

    async def remember_lifecycle_intent(self, intent: LifecycleIntent, at: datetime) -> None: ...


class DeletionUnitOfWork(Protocol):
    def transaction(
        self,
        session_digest: bytes,
        workflow_id: UUID,
    ) -> AbstractAsyncContextManager[DeletionTransaction]:
        """Actual actor account BEFORE session/workflow; source/effects/intents atomic.

        Resolving an original session digest for locking or receipt scoping is not a new
        login or a current mutation grant. Main owns SQL/proof implementation.
        """
        ...
