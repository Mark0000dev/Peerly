import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

from studymate.application.discovery.profiles import DiscoveryProfileSource
from studymate.application.idempotency import IntentKey
from studymate.application.profiles.goals import SavedGoal
from studymate.application.profiles.help_subjects import SavedHelpSubjects
from studymate.application.requests.ports import (
    ConversationReference,
    PairState,
    RequestIntent,
    RequestPreview,
    RequestTransaction,
)
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.limits import SendQuota, send_day
from studymate.domain.requests.states import ConnectionRequest
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    GoalContent,
    HelpRevision,
    HelpSubject,
    HelpSubjects,
)
from tests.unit.identity_store import NOW, IdentityStore
from tests.unit.test_discovery_profiles import source

SENDER = UUID(int=2)
PEER = UUID(int=3)
SUBJECT = UUID(int=7)
RELATIONSHIP = UUID(int=4)


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        self.sources = {owner: self.ready_source(owner) for owner in (SENDER, PEER)}
        self.previews: dict[UUID, RequestPreview] = {}
        self.requests: dict[UUID, ConnectionRequest] = {}
        self.intents: dict[tuple[UUID, str, str], RequestIntent] = {}
        self.conversations: dict[UUID, ConversationReference] = {}
        self.sends: list[tuple[UUID, datetime]] = []
        self.blocked = False
        self.expire_on_save = False
        self.fail_conversation = False
        self.bad_conversation = False
        self.expire_request_on_conversation = False
        self.lock = asyncio.Lock()

    def ready_source(self, owner: UUID) -> DiscoveryProfileSource:
        base = source(owner, self)
        assert base.setup.goal is not None
        saved = SavedGoal(
            replace(
                base.setup.goal.goal,
                content=GoalContent(
                    CanonicalSubjectRef(SUBJECT),
                    "Synthetic topic",
                    "Private synthetic source",
                    True,
                ),
            ),
            "Synthetic subject",
        )
        help_snapshot = SavedHelpSubjects(
            HelpRevision(owner, 1, HelpSubjects((HelpSubject(SUBJECT, "Synthetic help"),)), NOW),
            ("Synthetic subject",),
        )
        return replace(base, setup=replace(base.setup, goal=saved, help_subjects=help_snapshot))

    @asynccontextmanager
    async def transaction(self, peer_id: UUID) -> AsyncIterator[RequestTransaction]:
        assert peer_id.int > 0
        async with self.lock:
            before = (
                self.previews.copy(),
                self.requests.copy(),
                self.intents.copy(),
                self.conversations.copy(),
                self.sends.copy(),
            )
            try:
                yield self
            except BaseException:
                self.previews, self.requests, self.intents, self.conversations, self.sends = before
                raise

    async def profile_source(self, account_id: UUID) -> DiscoveryProfileSource | None:
        return self.sources.get(account_id)

    async def pair_blocked(self, actor_id: UUID, target_id: UUID) -> bool:
        assert AccountPair.between(actor_id, target_id) == AccountPair.between(SENDER, PEER)
        return self.blocked

    async def preview(self, preview_id: UUID) -> RequestPreview | None:
        return self.previews.get(preview_id)

    async def save_preview(self, preview: RequestPreview) -> None:
        self.previews[preview.id] = preview
        self.expire_session()

    async def request(self, request_id: UUID) -> ConnectionRequest | None:
        return self.requests.get(request_id)

    async def save_request(self, request: ConnectionRequest) -> None:
        if request.id not in self.requests:
            self.sends.append((request.context.sender_id, request.sent_at))
        self.requests[request.id] = request
        self.expire_session()

    def expire_session(self) -> None:
        if self.expire_on_save:
            self.clock = self.actor.session.expires_at

    async def intent(self, actor_id: UUID, operation: str, key: IntentKey) -> RequestIntent | None:
        return self.intents.get((actor_id, operation, key.value))

    async def remember_intent(
        self, actor_id: UUID, operation: str, key: IntentKey, intent: RequestIntent, at: datetime
    ) -> None:
        assert at == self.clock
        self.intents[actor_id, operation, key.value] = intent

    async def existing_pair(self, actor_id: UUID, peer_id: UUID, at: datetime) -> PairState | None:
        pair = AccountPair.between(actor_id, peer_id)
        if (
            not any(value.pair == pair for value in self.requests.values())
            and not self.conversations
        ):
            return None
        return await self.pair_state(actor_id, peer_id, at)

    async def observe_pair(self, actor_id: UUID, peer_id: UUID, at: datetime) -> PairState | None:
        before = self.requests.copy()
        try:
            return await self.existing_pair(actor_id, peer_id, at)
        finally:
            self.requests = before

    async def pair_state(self, actor_id: UUID, peer_id: UUID, at: datetime) -> PairState:
        pair = AccountPair.between(actor_id, peer_id)
        values = [
            request.effective(at) for request in self.requests.values() if request.pair == pair
        ]
        self.requests.update((request.id, request) for request in values)
        pending = next((request for request in values if request.pending), None)
        cooldowns = [
            until
            for request in values
            if request.context.sender_id == actor_id
            and (until := request.sender_cooldown_until) is not None
        ]
        return PairState(
            RELATIONSHIP,
            pair,
            pending,
            self.conversations.get(RELATIONSHIP),
            max(cooldowns, default=None),
        )

    async def quota(self, actor_id: UUID, at: datetime) -> SendQuota:
        return SendQuota(
            sum(
                request.context.sender_id == actor_id and request.effective(at).pending
                for request in self.requests.values()
            ),
            sum(owner == actor_id and send_day(when) == send_day(at) for owner, when in self.sends),
        )

    async def create_conversation(
        self, request: ConnectionRequest, at: datetime
    ) -> ConversationReference:
        assert at == self.clock
        if self.fail_conversation:
            raise RuntimeError("Synthetic conversation rollback")
        ref = ConversationReference(
            uuid4(),
            request.relationship_id,
            request.pair,
            uuid4() if self.bad_conversation else request.id,
        )
        self.conversations.setdefault(request.relationship_id, ref)
        if self.expire_request_on_conversation:
            self.clock = request.expires_at
        return self.conversations[request.relationship_id]

    def as_recipient(self) -> None:
        self.actor = replace(self.actor, session=replace(self.actor.session, account_id=PEER))
