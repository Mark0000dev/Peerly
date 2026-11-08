"""Typed atomic deletion simulation; actual SQL/proof/queue finality remains main-owned."""

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.lifecycle.deletion_ports import DeletionWorkflowAuthorization
from studymate.application.lifecycle.intents import LifecycleIntent
from studymate.domain.identity import Session
from studymate.domain.lifecycle.states import (
    AccountLifecycle,
    DeletionRevision,
    DeletionTransition,
    LifecycleOperation,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.lifecycle.ban_store import BanStore
from tests.unit.lifecycle.test_states import WORKFLOW
from tests.unit.operator.test_authorized_reads import HASHER

FOREIGN_ACCOUNT = UUID(int=901)


class DeletionStore(BanStore):
    def __init__(self) -> None:
        super().__init__()
        owner = self.actor.session.account_id
        self.targets[owner] = AccountLifecycle(owner)
        self.authorization = DeletionWorkflowAuthorization(
            WORKFLOW, owner, self.actor.session.id, NOW + timedelta(minutes=5)
        )  # Synthetic test interval, not a runtime TTL policy.
        self.proof_available = True
        self.authorization_override: DeletionWorkflowAuthorization | None = None
        self.deletion_sources: tuple[DeletionRevision, ...] = ()
        self.sessions = {
            self.actor.session.id: self.actor.session,
            UUID(int=900): Session(
                UUID(int=900), owner, NOW - timedelta(minutes=2), NOW + timedelta(hours=2)
            ),
            UUID(int=902): Session(
                UUID(int=902), FOREIGN_ACCOUNT, NOW - timedelta(minutes=2), NOW + timedelta(hours=2)
            ),
        }
        self.unused_verification_accounts = {owner, FOREIGN_ACCOUNT}
        self.delivery_accounts = {owner, FOREIGN_ACCOUNT}
        self.attributable_login_accounts = {owner, FOREIGN_ACCOUNT}
        self.unbound_login_flows = (uuid4(),)
        self.pending_contact_accounts = {owner, FOREIGN_ACCOUNT}
        self.pending_ai_accounts = {owner, FOREIGN_ACCOUNT}
        self.business_history = {
            owner: ("Private retained original business history",),
            FOREIGN_ACCOUNT: ("Foreign retained history",),
        }
        self.google_identity_accounts = {owner, FOREIGN_ACCOUNT}
        self.institutional_address_accounts = {owner, FOREIGN_ACCOUNT}
        self.identity_reads = 0
        self.switch_second_identity = False
        self.expire_after_target = False
        self.expire_workflow_after_apply = False
        self.expire_workflow_after_prior = False
        self.received_deletion_scope: tuple[bytes, UUID] | None = None

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        self.identity_reads += 1
        identity = await BanStore.lock_identity(self, secret_digest)
        if identity is not None and self.switch_second_identity and self.identity_reads > 1:
            return replace(identity, session=replace(identity.session, id=uuid4()))
        return identity

    async def revoke_session(self, session_id: UUID, at: datetime) -> None:
        assert session_id in self.sessions
        assert at.utcoffset() is not None
        raise AssertionError("Usecase must request all deletion effects through its atomic port")

    @asynccontextmanager
    async def deletion_transaction(
        self, digest: bytes, workflow_id: UUID
    ) -> AsyncIterator["DeletionStore"]:
        self.received_deletion_scope = digest, workflow_id
        original = None
        try:
            async with self.ban_transaction(digest, self.actor.session.account_id):
                # Snapshot only AFTER acquiring the fake serial lock: a failed waiter
                # must not roll back another transaction's already committed effects.
                original = (
                    self.deletion_sources,
                    self.sessions.copy(),
                    self.unused_verification_accounts.copy(),
                    self.delivery_accounts.copy(),
                    self.attributable_login_accounts.copy(),
                    self.pending_contact_accounts.copy(),
                    self.pending_ai_accounts.copy(),
                )
                yield self
        except BaseException:
            if original is not None:
                (
                    self.deletion_sources,
                    self.sessions,
                    self.unused_verification_accounts,
                    self.delivery_accounts,
                    self.attributable_login_accounts,
                    self.pending_contact_accounts,
                    self.pending_ai_accounts,
                ) = original
            raise

    async def authorized_deletion_workflow(
        self, session_digest: bytes, workflow_id: UUID
    ) -> DeletionWorkflowAuthorization | None:
        self.calls.append("workflow")
        if self.authorization_override is not None:
            return self.authorization_override
        if (
            not self.proof_available
            or session_digest != await HASHER.digest(CREDENTIAL)
            or workflow_id != self.authorization.id
        ):
            return None
        return self.authorization

    async def target_lifecycle(self, account_id: UUID) -> AccountLifecycle | None:
        result = await BanStore.target_lifecycle(self, account_id)
        if self.expire_after_target:
            self.clock = self.authorization.expires_at
        return result

    async def prior_lifecycle_intent(
        self, actor_id: UUID, operation: LifecycleOperation, key: IntentKey
    ) -> LifecycleIntent | None:
        result = await BanStore.prior_lifecycle_intent(self, actor_id, operation, key)
        if self.expire_workflow_after_prior:
            self.clock = self.authorization.expires_at
        return result

    async def apply_deletion_transition(self, transition: DeletionTransition) -> None:
        self.calls.append("delete_apply")
        source = transition.revision
        owner = source.account_id
        assert self.targets[owner] == transition.before
        self.targets[owner] = transition.after
        self.deletion_sources = (*self.deletion_sources, source)
        self.canonical = (*self.canonical, source.id)
        self.sessions = {
            identifier: session.revoke(source.deleted_at)
            if session.account_id == owner
            else session
            for identifier, session in self.sessions.items()
        }
        self.actor = replace(
            self.actor, deleted_at=source.deleted_at, session=self.sessions[self.actor.session.id]
        )
        for owned in (
            self.unused_verification_accounts,
            self.delivery_accounts,
            self.attributable_login_accounts,
            self.pending_contact_accounts,
            self.pending_ai_accounts,
        ):
            owned.discard(owner)
        if self.expire_after_apply:
            self.clock = self.actor.session.expires_at
        if self.expire_workflow_after_apply:
            self.clock = self.authorization.expires_at
        if self.fail_apply:
            raise StorageUnavailableError
        if self.pause_apply:
            self.entered.set()
            await self.release.wait()


@dataclass(frozen=True, slots=True)
class DeletionUnit:
    store: DeletionStore

    def transaction(
        self, session_digest: bytes, workflow_id: UUID
    ) -> AbstractAsyncContextManager[DeletionStore]:
        return self.store.deletion_transaction(session_digest, workflow_id)
