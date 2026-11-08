from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement

from studymate.application.operator.data import OperatorAccountDetail, OperatorAccountSummary
from studymate.application.operator.filters import OperatorAccountFilters, OperatorAccountLifecycle
from studymate.application.operator.ports import OperatorAccountWindow, OperatorMessageWindow
from studymate.domain.messaging import ChatConversation, ConfirmedMessage, MessageContent
from studymate.domain.onboarding import ProfileLifecycle
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.audit import (
    OPERATOR_ACCOUNT_PAGE_SIZE,
    OPERATOR_MESSAGE_PAGE_SIZE,
    OperatorAction,
    OperatorAudit,
)
from studymate.domain.relationships import AccountPair
from studymate.infrastructure.observability.tracing import current_origin
from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.operator.reads import (
    account_sources,
    account_summary,
    registration_snapshot,
)
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.discovery_exposure import read_discovery_exposure
from studymate.infrastructure.persistence.goals import SqlGoalTransaction
from studymate.infrastructure.persistence.help_subjects import SqlHelpTransaction
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_uploads import SqlMediaTransaction
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.onboarding_models import VisibilityRevisionRecord
from studymate.infrastructure.persistence.profile_models import ProfileRevisionRecord
from studymate.infrastructure.persistence.profiles import SqlProfileTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


def lifecycle_conditions(lifecycle: OperatorAccountLifecycle) -> tuple[ColumnElement[bool], ...]:
    if lifecycle == OperatorAccountLifecycle.ACTIVE:
        return (AccountRecord.banned_at.is_(None), AccountRecord.deleted_at.is_(None))
    if lifecycle == OperatorAccountLifecycle.BANNED:
        return (AccountRecord.banned_at.is_not(None),)
    if lifecycle == OperatorAccountLifecycle.DELETED:
        return (AccountRecord.deleted_at.is_not(None),)
    return ()


class OperatorAuditRecorder(Protocol):
    async def __call__(self, session: AsyncSession, audit: OperatorAudit) -> None: ...


@dataclass(slots=True)
class OperatorAuthority:
    account_id: UUID | None = None
    access: OperatorAccess | None = None


@dataclass(frozen=True, slots=True)
class SqlOperatorTransaction(SqlIdentityTransaction):
    recorder: OperatorAuditRecorder
    authority: OperatorAuthority = field(default_factory=OperatorAuthority)

    def authenticated(self, account_id: UUID) -> None:
        SqlIdentityTransaction.authenticated(self, account_id)
        self.authority.account_id = account_id

    async def operator_access(self, account_id: UUID) -> OperatorAccess | None:
        if self.authority.account_id != account_id:
            raise RuntimeError("Operator role lookup differs from the authenticated account")
        row = await self.session.scalar(
            select(OperatorAccessRevisionRecord)
            .join(
                OperatorAccessRecord,
                and_(
                    OperatorAccessRecord.account_id == OperatorAccessRevisionRecord.account_id,
                    OperatorAccessRecord.current_version == OperatorAccessRevisionRecord.version,
                ),
            )
            .join(
                ExternalIdentityRecord,
                ExternalIdentityRecord.account_id == OperatorAccessRecord.account_id,
            )
            .where(OperatorAccessRecord.account_id == account_id)
            .with_for_update(of=OperatorAccessRecord)
        )
        access = (
            OperatorAccess(row.account_id, row.version, row.active, row.changed_at)
            if row is not None
            else None
        )
        self.authority.access = (
            access if access is not None and access.is_active(await self.now()) else None
        )
        return access

    def checked_access(self) -> OperatorAccess:
        access = self.authority.access
        if access is None or access.account_id != self.authority.account_id or not access.active:
            raise RuntimeError("Private inspection lacks its actual current operator grant")
        return access

    async def search_operator_accounts(
        self, filters: OperatorAccountFilters, window: OperatorAccountWindow
    ) -> tuple[OperatorAccountSummary, ...]:
        self.checked_access()
        statement = account_sources().where(AccountRecord.created_at <= window.as_of)
        if filters.account_id is not None:
            statement = statement.where(AccountRecord.id == filters.account_id)
        if filters.google_link_id is not None:
            statement = statement.where(ExternalIdentityRecord.id == filters.google_link_id)
        if filters.google_issuer is not None:
            statement = statement.where(ExternalIdentityRecord.issuer == filters.google_issuer)
        if filters.google_subject is not None:
            statement = statement.where(ExternalIdentityRecord.subject == filters.google_subject)
        if filters.institutional_email is not None:
            statement = statement.where(
                InstitutionalBindingRecord.email == filters.institutional_email.value
            )
        if filters.name is not None:
            literal = filters.name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            statement = statement.where(
                ProfileRevisionRecord.display_name.ilike("%" + literal + "%", escape="\\")
            )
        statement = statement.where(*lifecycle_conditions(filters.lifecycle))
        if filters.hidden is not None:
            statement = statement.where(
                VisibilityRevisionRecord.hidden_at.is_not(None)
                if filters.hidden
                else VisibilityRevisionRecord.hidden_at.is_(None)
            )
        if filters.created_from is not None:
            statement = statement.where(AccountRecord.created_at >= filters.created_from)
        if filters.created_before is not None:
            statement = statement.where(AccountRecord.created_at < filters.created_before)
        if window.before is not None:
            statement = statement.where(
                tuple_(AccountRecord.created_at, AccountRecord.id)
                < tuple_(window.before.created_at, window.before.account_id)
            )
        rows = (
            await self.session.execute(
                statement.order_by(AccountRecord.created_at.desc(), AccountRecord.id.desc()).limit(
                    OPERATOR_ACCOUNT_PAGE_SIZE + 1
                )
            )
        ).all()
        return tuple(account_summary(*row) for row in rows)

    async def operator_account(self, account_id: UUID) -> OperatorAccountDetail | None:
        self.checked_access()
        row = (
            await self.session.execute(account_sources().where(AccountRecord.id == account_id))
        ).one_or_none()
        if row is None:
            return None
        account, google, binding, profile, visibility = row
        summary = account_summary(account, google, binding, profile, visibility)
        return OperatorAccountDetail(
            summary,
            await SqlProfileTransaction(self.session).profile(account_id, profile.version)
            if profile is not None
            else None,
            await SqlMediaTransaction(self.session).current_photo(account_id),
            await SqlGoalTransaction(self.session).active_goal(account_id),
            await SqlHelpTransaction(self.session).help_subjects(account_id),
            ProfileLifecycle(
                visibility.account_id,
                visibility.completed_at,
                visibility.version,
                visibility.hidden_at,
                visibility.changed_at,
            )
            if visibility is not None
            else None,
            await read_discovery_exposure(self.session, account_id),
            await registration_snapshot(self.session, account_id),
        )

    async def operator_conversation(self, conversation_id: UUID) -> ChatConversation | None:
        self.checked_access()
        row = await self.session.get(ConversationRecord, conversation_id)
        if row is None:
            return None
        return ChatConversation(
            row.id,
            row.relationship_id,
            AccountPair(row.low_id, row.high_id),
            row.request_id,
            row.accepted_request_version,
            row.next_message_sequence,
        )

    async def operator_messages(
        self, conversation_id: UUID, window: OperatorMessageWindow
    ) -> tuple[ConfirmedMessage, ...]:
        self.checked_access()
        statement = select(MessageRecord).where(
            MessageRecord.conversation_id == conversation_id,
            MessageRecord.sequence <= window.anchor_sequence,
        )
        if window.before_sequence is not None:
            statement = statement.where(MessageRecord.sequence < window.before_sequence)
        rows = tuple(
            await self.session.scalars(
                statement.order_by(MessageRecord.sequence.desc()).limit(
                    OPERATOR_MESSAGE_PAGE_SIZE + 1
                )
            )
        )
        return tuple(
            ConfirmedMessage(
                row.id,
                row.operation_id,
                row.conversation_id,
                AccountPair(row.low_id, row.high_id),
                row.author_id,
                row.client_message_id,
                row.sequence,
                MessageContent(row.text, row.image_id),
                row.sent_at,
            )
            for row in rows
        )

    async def save_operator_audit(self, audit: OperatorAudit) -> None:
        actual = self.checked_access()
        if audit.access != actual or audit.at < actual.changed_at:
            raise RuntimeError("Inspection audit differs from the actual locked grant or its time")
        origin = current_origin()
        resource_kind = {
            OperatorAction.SEARCH_ACCOUNTS: "account",
            OperatorAction.READ_ACCOUNT: "account",
            OperatorAction.READ_CONVERSATION_MESSAGES: "conversation",
            OperatorAction.SEARCH_EVENTS: "event",
            OperatorAction.READ_EVENT: "event",
            OperatorAction.READ_AUDIT: "audit",
            OperatorAction.SEARCH_REPORTS: "report",
            OperatorAction.READ_REPORT: "report",
            OperatorAction.READ_MEDIA: "profile_media",
        }[audit.action]
        self.session.add(
            OperatorAuditRecord(
                id=audit.id,
                operator_id=actual.account_id,
                operator_access_version=actual.version,
                operator_access_active=actual.active,
                action=audit.action.value,
                resource_kind=resource_kind,
                requested_id=audit.requested.id if audit.requested is not None else None,
                result_ids=[ref.id for ref in audit.results],
                requested_media_owner_id=audit.media_request.account_id
                if audit.media_request is not None
                else None,
                requested_media_attempt_id=audit.media_request.attempt_id
                if audit.media_request is not None
                else None,
                requested_media_kind=audit.media_request.kind.value
                if audit.media_request is not None
                else None,
                actual_source_upload_id=audit.actual_source_upload_id,
                outcome=audit.outcome.value,
                query_fingerprint=audit.query_fingerprint,
                occurred_at=audit.at,
                http_request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()
        await self.recorder(self.session, audit)


@dataclass(frozen=True, slots=True)
class SqlOperatorUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorTransaction(session, self.recorder)
