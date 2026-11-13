from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID

from studymate.application.errors import StorageUnavailableError
from studymate.application.requests.response_options_ports import ResponseOptionsContext
from tests.unit.identity_store import IdentityStore
from tests.unit.requests.store import PEER, SENDER, Store
from tests.unit.requests.test_states import request


class ResponseStore(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(
            self.actor,
            session=replace(self.actor.session, account_id=PEER),
            activation_complete=True,
        )
        sources = Store().sources
        self.context = ResponseOptionsContext(request(), sources[PEER], sources[SENDER], False)
        self.source_reads = 0
        self.unavailable = False
        self.storage_failure = False
        self.expire_after_read = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["ResponseStore"]:
        yield self

    async def response_context(
        self, actor_id: UUID, request_id: UUID
    ) -> ResponseOptionsContext | None:
        assert actor_id == PEER
        assert request_id.int > 0
        self.source_reads += 1
        if self.storage_failure:
            raise StorageUnavailableError
        if self.expire_after_read:
            self.clock = self.actor.session.expires_at
        return None if self.unavailable else self.context
