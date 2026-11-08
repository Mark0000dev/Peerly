from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.requests.viewing import (
    AcknowledgeRequestViewed,
    RequestViewIntent,
    RequestViewTransaction,
    ViewRequestCommand,
)
from studymate.domain.requests.states import RequestUnavailableError
from studymate.domain.requests.views import RequestDisclosure, RequestViewReceipt
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore
from tests.unit.requests.test_usecases import FINGERPRINTER, HASHER, key


class ViewStore(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        self.source = RequestDisclosure(uuid4(), self.actor.session.account_id, uuid4(), 2, NOW)
        self.intents: dict[str, RequestViewIntent] = {}
        self.receipt: RequestViewReceipt | None = None
        self.expire_on_write = False
        self.bad_source = False
        self.bad_receipt = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[RequestViewTransaction]:
        before = self.intents.copy(), self.receipt
        try:
            yield self
        except BaseException:
            self.intents, self.receipt = before
            raise

    async def disclosure(
        self, viewer_id: UUID, request_id: UUID, disclosure_id: UUID
    ) -> RequestDisclosure | None:
        if self.bad_source:
            return replace(self.source, viewer_id=uuid4())
        return (
            self.source
            if (viewer_id, request_id, disclosure_id)
            == (self.source.viewer_id, self.source.request_id, self.source.id)
            else None
        )

    async def view_intent(self, actor_id: UUID, key: IntentKey) -> RequestViewIntent | None:
        assert actor_id == self.actor.session.account_id
        return self.intents.get(key.value)

    async def acknowledge(self, source: RequestViewReceipt) -> RequestViewReceipt:
        if self.bad_receipt:
            return replace(source, viewer_id=uuid4())
        if self.receipt is None:
            self.receipt = source
        return self.receipt

    async def remember_view(
        self, actor_id: UUID, key: IntentKey, intent: RequestViewIntent, at: datetime
    ) -> None:
        assert actor_id == self.actor.session.account_id
        assert at == self.clock
        self.intents[key.value] = intent
        if self.expire_on_write:
            self.clock = self.actor.session.expires_at

    def command(self) -> ViewRequestCommand:
        return ViewRequestCommand(CREDENTIAL, self.source.request_id, self.source.id, key())


def usecase(store: ViewStore) -> AcknowledgeRequestViewed:
    return AcknowledgeRequestViewed(store, HASHER, FINGERPRINTER)


async def test_explicit_ack_replays_original_and_deduplicates_source_revision() -> None:
    store = ViewStore()
    command = store.command()
    receipt = await usecase(store)(command)
    assert receipt.disclosure_id == store.source.id
    assert await usecase(store)(command) == receipt
    store.source = replace(store.source, id=uuid4())
    second_command = store.command()
    assert await usecase(store)(second_command) == receipt
    assert set(store.intents) == {command.key.value, second_command.key.value}
    with pytest.raises(IdempotencyConflictError):
        await usecase(store)(replace(command, disclosure_id=store.source.id))


@pytest.mark.parametrize("field", ["request_id", "disclosure_id"])
async def test_unknown_or_foreign_disclosure_is_unavailable(field: str) -> None:
    store = ViewStore()
    command = store.command()
    command = (
        replace(command, request_id=uuid4())
        if field == "request_id"
        else replace(command, disclosure_id=uuid4())
    )
    with pytest.raises(RequestUnavailableError):
        await usecase(store)(command)
    assert store.receipt is None
    assert not store.intents


async def test_live_actor_permission_rechecked_before_original_receipt() -> None:
    store = ViewStore()
    command = store.command()
    await usecase(store)(command)
    store.actor = replace(store.actor, banned=True)
    with pytest.raises(StudentActionDeniedError):
        await usecase(store)(command)
    store.actor = replace(store.actor, banned=False, activation_complete=False)
    with pytest.raises(StudentActionDeniedError):
        await usecase(store)(command)


async def test_expired_session_rolls_back_ack_and_intent() -> None:
    store = ViewStore()
    store.expire_on_write = True
    with pytest.raises(UnauthenticatedError):
        await usecase(store)(store.command())
    assert store.receipt is None
    assert not store.intents


@pytest.mark.parametrize("bad_source", [True, False])
async def test_adapter_cannot_return_another_viewers_source(bad_source: bool) -> None:
    store = ViewStore()
    store.bad_source = bad_source
    store.bad_receipt = not bad_source
    with pytest.raises(RuntimeError, match="another owned source"):
        await usecase(store)(store.command())
    assert store.receipt is None
    assert not store.intents
