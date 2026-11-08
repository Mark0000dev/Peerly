"""Transactional typed ban fake; lock/effect simulation is NOT PostgreSQL acceptance."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.lifecycle.intents import LifecycleIntent
from studymate.domain.lifecycle.states import (
    AccountLifecycle,
    BanRevision,
    BanTransition,
    LifecycleOperation,
)
from tests.unit.identity_store import CREDENTIAL
from tests.unit.lifecycle.test_states import ACCOUNT
from tests.unit.operator.store import Store
from tests.unit.operator.test_authorized_reads import HASHER


class BanStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.targets = {ACCOUNT: AccountLifecycle(ACCOUNT)}
        self.intents: dict[tuple[UUID, LifecycleOperation, str], LifecycleIntent] = {}
        self.sources: tuple[BanRevision, ...] = ()
        self.canonical: tuple[UUID, ...] = ()
        self.received_scope: tuple[bytes, UUID] | None = None
        self.calls: list[str] = []
        self.serial = asyncio.Lock()
        self.missing_identity = False
        self.target_override: AccountLifecycle | None = None
        self.intent_override: LifecycleIntent | None = None
        self.fail_apply = False
        self.fail_remember = False
        self.fail_commit = False
        self.expire_after_apply = False
        self.expire_after_prior = False
        self.pause_apply = False
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        if self.missing_identity or secret_digest != await HASHER.digest(CREDENTIAL):
            return None
        return self.actor

    @asynccontextmanager
    async def ban_transaction(self, digest: bytes, target_id: UUID) -> AsyncIterator["BanStore"]:
        self.received_scope = digest, target_id
        async with self.serial:
            original = (
                self.targets.copy(),
                self.intents.copy(),
                self.sources,
                self.canonical,
                self.actor,
            )
            try:
                async with Store.transaction(self):
                    yield self
                    if self.fail_commit:
                        raise StorageUnavailableError
            except BaseException:
                self.targets, self.intents, self.sources, self.canonical, self.actor = original
                raise

    async def target_lifecycle(self, account_id: UUID) -> AccountLifecycle | None:
        self.queried()
        self.calls.append("target")
        return (
            self.target_override
            if self.target_override is not None
            else self.targets.get(account_id)
        )

    async def prior_lifecycle_intent(
        self, actor_id: UUID, operation: LifecycleOperation, key: IntentKey
    ) -> LifecycleIntent | None:
        self.queried()
        self.calls.append("prior")
        if self.expire_after_prior:
            self.clock = self.actor.session.expires_at
        return (
            self.intent_override
            if self.intent_override is not None
            else self.intents.get((actor_id, operation, key.value))
        )

    async def apply_ban_transition(self, transition: BanTransition) -> None:
        self.calls.append("apply")
        source = transition.revision
        assert source is not None
        assert self.targets[source.account_id] == transition.before
        self.targets[source.account_id] = transition.after
        self.sources = (*self.sources, source)
        self.canonical = (*self.canonical, source.id)
        if source.account_id == self.actor.session.account_id:
            self.actor = replace(self.actor, banned=transition.after.banned_at is not None)
        if self.expire_after_apply:
            self.clock = self.actor.session.expires_at
        if self.fail_apply:
            raise StorageUnavailableError
        if self.pause_apply:
            self.entered.set()
            await self.release.wait()

    async def remember_lifecycle_intent(self, intent: LifecycleIntent, at: datetime) -> None:
        assert at <= self.clock
        self.calls.append("remember")
        key = intent.actor_id, intent.operation, intent.key.value
        assert key not in self.intents
        self.intents[key] = intent
        if self.fail_remember:
            raise StorageUnavailableError


@dataclass(frozen=True, slots=True)
class BanUnit:
    store: BanStore

    def transaction(
        self, actor_secret_digest: bytes, target_account_id: UUID
    ) -> AbstractAsyncContextManager[BanStore]:
        return self.store.ban_transaction(actor_secret_digest, target_account_id)
