"""Retained direct claim joins without student visibility filters or identity inference."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.operator.identity_links_data import (
    IDENTITY_LINKS_PAGE_SIZE,
    OperatorGoogleClaim,
    OperatorIdentityAccount,
    OperatorIdentityLink,
    OperatorInstitutionalClaim,
)
from studymate.application.operator.identity_links_ports import OperatorIdentityLinksWindow
from studymate.domain.identity import StudentEmail
from studymate.infrastructure.operator.transactions import (
    OperatorAuditRecorder,
    SqlOperatorTransaction,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.transactions import open_transaction


def identity_account(
    account: AccountRecord,
    google: ExternalIdentityRecord | None,
    institutional: InstitutionalBindingRecord | None,
) -> OperatorIdentityAccount:
    return OperatorIdentityAccount(
        account.id,
        account.created_at,
        account.banned_at,
        account.deleted_at,
        OperatorGoogleClaim(
            google.id, google.issuer, google.subject, google.created_at, google.retired_at
        )
        if google is not None
        else None,
        OperatorInstitutionalClaim(
            StudentEmail(institutional.email),
            institutional.verified_at,
            institutional.revoked_at,
            institutional.retired_at,
        )
        if institutional is not None
        else None,
    )


@dataclass(frozen=True, slots=True)
class SqlOperatorIdentityLinksTransaction(SqlOperatorTransaction):
    async def identity_links_target(self, account_id: UUID) -> OperatorIdentityAccount | None:
        self.checked_access()
        row = (
            await self.session.execute(
                select(AccountRecord, ExternalIdentityRecord, InstitutionalBindingRecord)
                .outerjoin(
                    ExternalIdentityRecord,
                    ExternalIdentityRecord.account_id == AccountRecord.id,
                )
                .outerjoin(
                    InstitutionalBindingRecord,
                    InstitutionalBindingRecord.account_id == AccountRecord.id,
                )
                .where(AccountRecord.id == account_id)
            )
        ).one_or_none()
        return identity_account(*row) if row is not None else None

    async def identity_links(
        self,
        target: OperatorIdentityAccount,
        window: OperatorIdentityLinksWindow,
    ) -> tuple[OperatorIdentityLink, ...]:
        self.checked_access()
        conditions = []
        if target.google is not None:
            conditions.append(
                and_(
                    ExternalIdentityRecord.issuer == target.google.issuer,
                    ExternalIdentityRecord.subject == target.google.subject,
                    ExternalIdentityRecord.created_at <= window.as_of,
                )
            )
        if target.institutional is not None:
            conditions.append(
                and_(
                    InstitutionalBindingRecord.email == target.institutional.email.value,
                    InstitutionalBindingRecord.verified_at <= window.as_of,
                )
            )
        if not conditions:
            return ()
        statement = (
            select(AccountRecord, ExternalIdentityRecord, InstitutionalBindingRecord)
            .outerjoin(
                ExternalIdentityRecord,
                ExternalIdentityRecord.account_id == AccountRecord.id,
            )
            .outerjoin(
                InstitutionalBindingRecord,
                InstitutionalBindingRecord.account_id == AccountRecord.id,
            )
            .where(
                AccountRecord.id != target.account_id,
                AccountRecord.created_at <= window.as_of,
                or_(*conditions),
            )
        )
        if window.before is not None:
            statement = statement.where(
                tuple_(AccountRecord.created_at, AccountRecord.id)
                < tuple_(window.before.before_created_at, window.before.before_account_id)
            )
        rows = (
            await self.session.execute(
                statement.order_by(AccountRecord.created_at.desc(), AccountRecord.id.desc()).limit(
                    IDENTITY_LINKS_PAGE_SIZE + 1
                )
            )
        ).all()
        result = []
        for row in rows:
            account = identity_account(*row)
            google = account.google
            institutional = account.institutional
            result.append(
                OperatorIdentityLink(
                    account,
                    google is not None
                    and target.google is not None
                    and google.issuer == target.google.issuer
                    and google.subject == target.google.subject
                    and google.created_at <= window.as_of,
                    institutional is not None
                    and target.institutional is not None
                    and institutional.email == target.institutional.email
                    and institutional.verified_at <= window.as_of,
                )
            )
        return tuple(result)


@dataclass(frozen=True, slots=True)
class SqlOperatorIdentityLinksUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]
    recorder: OperatorAuditRecorder

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlOperatorIdentityLinksTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlOperatorIdentityLinksTransaction(session, self.recorder)
