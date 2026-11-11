from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

from studymate.application.errors import StorageUnavailableError
from studymate.application.operator.data import (
    OperatorAccountDetail,
    OperatorAccountSummary,
    StoredGoogleLink,
)
from studymate.application.operator.filters import OperatorAccountFilters, OperatorAccountLifecycle
from studymate.application.operator.ports import OperatorAccountWindow, OperatorMessageWindow
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.domain.messaging import ChatConversation, ConfirmedMessage, MessageContent
from studymate.domain.onboarding import ProfileLifecycle
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.audit import (
    OPERATOR_ACCOUNT_PAGE_SIZE,
    OPERATOR_MESSAGE_PAGE_SIZE,
    OperatorAudit,
)
from studymate.domain.profiles import DisplayName, OnboardingTask, ProfileBasics, ProfileRevision
from studymate.domain.relationships import AccountPair
from tests.unit.identity_store import NOW, IdentityStore

TARGET = UUID(int=10)


def target(account_id: UUID = TARGET) -> OperatorAccountDetail:
    profile = ProfileRevision(
        account_id,
        1,
        ProfileBasics(DisplayName("Private original name")),
        OnboardingTask.FIND_HELP,
        NOW,
    )
    identity = StoredGoogleLink(uuid4(), account_id, GOOGLE_ISSUER, "private-stored-subject", NOW)
    summary = OperatorAccountSummary(
        account_id,
        NOW - timedelta(days=1),
        NOW,
        NOW,
        identity,
        None,
        profile.version,
        profile.basics.display_name,
        NOW,
    )
    return OperatorAccountDetail(
        summary,
        profile,
        None,
        None,
        None,
        ProfileLifecycle(account_id, NOW, 1, NOW, NOW),
        None,
        None,
    )


class Store(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        # No fallback role. Tests must assign an explicit synthetic DB-source value.
        self.access: OperatorAccess | None = None
        self.audit: list[OperatorAudit] = []
        self.details = {TARGET: target()}
        pair = AccountPair.between(UUID(int=20), UUID(int=21))
        self.conversation = ChatConversation(uuid4(), uuid4(), pair, uuid4(), 2, 1)
        self.messages: tuple[ConfirmedMessage, ...] = ()
        self.private_queries = 0
        self.expire_after_role = False
        self.fail_audit = False
        self.expire_after_query = False
        self.expire_after_audit = False
        self.last_window: OperatorAccountWindow | None = None
        self.account_rows: tuple[OperatorAccountSummary, ...] | None = None
        self.message_rows: tuple[ConfirmedMessage, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["Store"]:
        before = self.audit.copy()
        try:
            yield self
        except BaseException:
            self.audit = before
            raise

    def assign_explicit_operator(self) -> None:
        self.access = OperatorAccess(self.actor.session.account_id, 1, True, NOW)

    async def operator_access(self, account_id: UUID) -> OperatorAccess | None:
        assert account_id == self.actor.session.account_id
        if self.expire_after_role:
            self.clock = self.actor.session.expires_at
        return self.access

    def queried(self) -> None:
        self.private_queries += 1
        if self.expire_after_query:
            self.clock = self.actor.session.expires_at

    async def save_operator_audit(self, audit: OperatorAudit) -> None:
        self.audit.append(audit)
        if self.fail_audit:
            raise StorageUnavailableError
        if self.expire_after_audit:
            self.clock = self.actor.session.expires_at

    async def operator_account(self, account_id: UUID) -> OperatorAccountDetail | None:
        self.queried()
        return self.details.get(account_id)

    async def search_operator_accounts(
        self, filters: OperatorAccountFilters, window: OperatorAccountWindow
    ) -> tuple[OperatorAccountSummary, ...]:
        self.queried()
        self.last_window = window
        if self.account_rows is not None:
            return self.account_rows
        rows = [value.account for value in self.details.values()]
        if filters.account_id is not None:
            rows = [row for row in rows if row.account_id == filters.account_id]
        if filters.lifecycle == OperatorAccountLifecycle.ACTIVE:
            rows = [row for row in rows if row.banned_at is None and row.deleted_at is None]
        if filters.lifecycle == OperatorAccountLifecycle.BANNED:
            rows = [row for row in rows if row.banned_at is not None]
        if filters.lifecycle == OperatorAccountLifecycle.DELETED:
            rows = [row for row in rows if row.deleted_at is not None]
        rows = [
            row
            for row in rows
            if row.created_at <= window.as_of
            and (
                window.before is None
                or (row.created_at, row.account_id.int)
                < (window.before.created_at, window.before.account_id.int)
            )
        ]
        return tuple(
            sorted(rows, key=lambda row: (row.created_at, row.account_id.int), reverse=True)
        )[: OPERATOR_ACCOUNT_PAGE_SIZE + 1]

    async def operator_conversation(self, conversation_id: UUID) -> ChatConversation | None:
        self.queried()
        return self.conversation if conversation_id == self.conversation.id else None

    async def operator_messages(
        self, conversation_id: UUID, window: OperatorMessageWindow
    ) -> tuple[ConfirmedMessage, ...]:
        self.queried()
        assert conversation_id == self.conversation.id
        if self.message_rows is not None:
            return self.message_rows
        return tuple(
            message
            for message in reversed(self.messages)
            if message.sequence <= window.anchor_sequence
            and (window.before_sequence is None or message.sequence < window.before_sequence)
        )[: OPERATOR_MESSAGE_PAGE_SIZE + 1]

    def append_message(self) -> ConfirmedMessage:
        value = ConfirmedMessage(
            uuid4(),
            uuid4(),
            self.conversation.id,
            self.conversation.pair,
            self.conversation.pair.low,
            uuid4(),
            self.conversation.next_message_sequence,
            MessageContent("Private stored conversation text"),
            NOW,
        )
        self.messages = (*self.messages, value)
        self.conversation = replace(self.conversation, next_message_sequence=value.sequence + 1)
        return value
