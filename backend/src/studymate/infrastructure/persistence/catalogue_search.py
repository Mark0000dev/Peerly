from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

from sqlalchemy import exists, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.catalogue import (
    CatalogueCursor,
    CataloguePage,
    CatalogueQuery,
    CatalogueTransaction,
)
from studymate.domain.catalogue import Subject
from studymate.infrastructure.persistence.catalogue_models import SubjectAliasRecord, SubjectRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlCatalogueTransaction(SqlIdentityTransaction):
    async def search_subjects(self, query: CatalogueQuery) -> CataloguePage:
        statement = select(SubjectRecord).where(SubjectRecord.archived_at.is_(None))
        if query.query:
            alias_match = exists(
                select(SubjectAliasRecord.subject_id).where(
                    SubjectAliasRecord.subject_id == SubjectRecord.id,
                    SubjectAliasRecord.normalized_alias.contains(query.query, autoescape=True),
                )
            )
            statement = statement.where(
                or_(
                    SubjectRecord.normalized_name.contains(query.query, autoescape=True),
                    alias_match,
                )
            )
        if query.cursor is not None:
            statement = statement.where(
                tuple_(SubjectRecord.normalized_name, SubjectRecord.id)
                > (query.cursor.normalized_name, query.cursor.subject_id)
            )
        records = tuple(
            await self.session.scalars(
                statement.order_by(SubjectRecord.normalized_name, SubjectRecord.id).limit(
                    query.limit + 1
                )
            )
        )
        selected = records[: query.limit]
        if not selected:
            return CataloguePage((), None)
        aliases: dict[UUID, list[str]] = {record.id: [] for record in selected}
        for alias in await self.session.scalars(
            select(SubjectAliasRecord)
            .where(SubjectAliasRecord.subject_id.in_(tuple(aliases)))
            .order_by(SubjectAliasRecord.subject_id, SubjectAliasRecord.slot)
        ):
            aliases[alias.subject_id].append(alias.name)
        items = tuple(
            Subject(record.id, record.name, tuple(aliases[record.id]), record.created_at)
            for record in selected
        )
        last = selected[-1]
        cursor = (
            CatalogueCursor(last.normalized_name, last.id, query.query)
            if len(records) > query.limit
            else None
        )
        return CataloguePage(items, cursor)


@dataclass(frozen=True, slots=True)
class SqlCatalogueUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[CatalogueTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlCatalogueTransaction(session)
