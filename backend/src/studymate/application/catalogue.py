from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from studymate.application.identity.sessions import (
    IdentityReader,
    SessionCredential,
    SessionHasher,
    require_verified_student,
)
from studymate.domain.catalogue import Subject
from studymate.domain.text import plain_text

MAX_PAGE_SIZE = 50
MAX_NORMALIZED_KEY = 240


@dataclass(frozen=True, slots=True)
class CatalogueCursor:
    normalized_name: str = field(repr=False)
    subject_id: UUID
    query_key: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not 1 <= len(self.normalized_name) <= MAX_NORMALIZED_KEY
            or len(self.query_key) > MAX_NORMALIZED_KEY
        ):
            raise ValueError("Catalogue cursor is outside the allowed range")


@dataclass(frozen=True, slots=True)
class CatalogueQuery:
    query: str = field(default="", repr=False)
    limit: int = 20
    cursor: CatalogueCursor | None = None

    def __post_init__(self) -> None:
        normalized = plain_text(self.query, minimum=0, maximum=80, collapse_spaces=True).casefold()
        if isinstance(self.limit, bool) or not 1 <= self.limit <= MAX_PAGE_SIZE:
            raise ValueError("Catalogue page size is outside the allowed range")
        if self.cursor is not None and self.cursor.query_key != normalized:
            raise ValueError("Catalogue cursor belongs to a different search")
        object.__setattr__(self, "query", normalized)


@dataclass(frozen=True, slots=True)
class CataloguePage:
    items: tuple[Subject, ...]
    next_cursor: CatalogueCursor | None


class CatalogueTransaction(IdentityReader, Protocol):
    async def search_subjects(self, query: CatalogueQuery) -> CataloguePage: ...


class CatalogueUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[CatalogueTransaction]: ...


@dataclass(frozen=True, slots=True)
class SearchSubjects:
    unit_of_work: CatalogueUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential, query: CatalogueQuery) -> CataloguePage:
        async with self.unit_of_work.transaction() as transaction:
            await require_verified_student(transaction, await self.hasher.digest(credential))
            return await transaction.search_subjects(query)
