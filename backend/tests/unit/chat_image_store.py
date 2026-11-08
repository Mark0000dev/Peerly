from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from typing import Self
from uuid import UUID, uuid4

from studymate.application.chat_images.start import ChatImageIntent
from studymate.application.idempotency import IntentKey
from studymate.application.media.uploads import UploadBudget
from studymate.application.messaging.ports import ConversationAccess
from studymate.domain.chat_images import ChatImagePreparation
from studymate.domain.messaging import ChatConversation, MessageOperation
from studymate.domain.relationships import AccountPair
from tests.unit.identity_store import IdentityStore


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        pair = AccountPair.between(self.actor.session.account_id, UUID(int=3))
        self.access: ConversationAccess | None = ConversationAccess(
            ChatConversation(uuid4(), uuid4(), pair, uuid4(), 2, 1), True, False, False, False
        )
        self.intents: dict[IntentKey, ChatImageIntent] = {}
        self.images: dict[UUID, ChatImagePreparation] = {}
        self.operation: MessageOperation | None = None
        self.budget = UploadBudget(0, None, 0, None)
        self.expire_after_write = False
        self.expire_after_replay = False
        self.capacity_checks = 0

    @asynccontextmanager
    async def transaction(self, conversation_id: UUID) -> AsyncIterator[Self]:
        assert self.access is None or self.access.conversation.id == conversation_id
        before = self.images.copy(), self.intents.copy()
        try:
            yield self
        except BaseException:
            self.images, self.intents = before
            raise

    async def conversation(
        self, actor_id: UUID, _conversation_id: UUID
    ) -> ConversationAccess | None:
        assert actor_id == self.actor.session.account_id
        return self.access

    async def image_start_intent(self, actor_id: UUID, key: IntentKey) -> ChatImageIntent | None:
        assert actor_id == self.actor.session.account_id
        if self.expire_after_replay:
            self.clock = self.actor.session.expires_at
        return self.intents.get(key)

    async def message_operation(
        self, actor_id: UUID, _conversation_id: UUID, _client_message_id: UUID
    ) -> MessageOperation | None:
        assert actor_id == self.actor.session.account_id
        return self.operation

    async def client_image(
        self, actor_id: UUID, _conversation_id: UUID, client_message_id: UUID
    ) -> ChatImagePreparation | None:
        assert actor_id == self.actor.session.account_id
        return self.images.get(client_message_id)

    async def expire_pending_images(self, actor_id: UUID, at: datetime) -> None:
        assert actor_id == self.actor.session.account_id
        self.images = {key: image.expire(at) for key, image in self.images.items()}

    async def image_budget(self, actor_id: UUID, _since: datetime) -> UploadBudget:
        assert actor_id == self.actor.session.account_id
        self.capacity_checks += 1
        return self.budget

    async def create_image(self, image: ChatImagePreparation) -> None:
        assert image.client_message_id not in self.images
        self.images[image.client_message_id] = image

    async def remember_image_start(
        self, actor_id: UUID, key: IntentKey, intent: ChatImageIntent, _at: datetime
    ) -> None:
        assert actor_id == self.actor.session.account_id
        self.intents[key] = intent
        if self.expire_after_write:
            self.clock = self.actor.session.expires_at
