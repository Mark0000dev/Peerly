"""One atomic owner reference-data transaction, never an account or consent bootstrap."""

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.domain.bootstrap_data.inputs import CatalogueProvenance
from studymate.domain.catalogue import Subject
from studymate.domain.registration import (
    PolicyKind,
    PolicyReference,
    PolicyVersion,
    PublishedPolicy,
)


class BootstrapDataTransaction(Protocol):
    async def now(self) -> datetime: ...

    async def policy_version(
        self, kind: PolicyKind, version: PolicyVersion
    ) -> PublishedPolicy | None: ...

    async def latest_reference(self, kind: PolicyKind) -> PolicyReference | None: ...

    async def add_policy(self, policy: PublishedPolicy) -> None: ...

    async def current_reference(self, kind: PolicyKind, at: datetime) -> PolicyReference | None: ...

    async def manifest(self, version: str) -> CatalogueProvenance | None: ...

    async def subjects(
        self, identities: tuple[UUID, ...], names: tuple[str, ...]
    ) -> tuple[Subject, ...]: ...

    async def add_subjects(self, subjects: tuple[Subject, ...]) -> None: ...

    async def add_manifest(self, source: CatalogueProvenance) -> None: ...


class BootstrapDataUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[BootstrapDataTransaction]:
        """Serialize only this CLI capability; rollback every write on conflict/failure."""
        ...


class BootstrapDatabaseConfigurationError(Exception):
    """The explicit DATABASE_URL is missing or not an async PostgreSQL URL."""


class BootstrapDatabaseOperationError(Exception):
    """Non-success database failure whose statement/parameters must not reach CLI output."""
