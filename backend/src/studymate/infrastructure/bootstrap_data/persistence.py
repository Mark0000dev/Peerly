"""Actual immutable policies/subjects and atomic retained catalogue provenance."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.domain.bootstrap_data.inputs import CatalogueProvenance
from studymate.domain.catalogue import Subject, subject_key
from studymate.domain.registration import (
    PolicyKind,
    PolicyReference,
    PolicyVersion,
    PublishedPolicy,
)
from studymate.infrastructure.bootstrap_data.models import BootstrapCatalogueManifestRecord
from studymate.infrastructure.persistence.catalogue_models import SubjectAliasRecord, SubjectRecord
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.registration import SqlRegistrationTransaction
from studymate.infrastructure.persistence.registration_models import PolicyDocumentRecord
from studymate.infrastructure.persistence.transactions import open_transaction

# Capability-specific two-int transaction lock: no user/account/pair lock namespace.
BOOTSTRAP_LOCK_NAMESPACE = 0x504C4244
BOOTSTRAP_LOCK_KEY = 1


@dataclass(frozen=True, slots=True)
class SqlBootstrapDataTransaction:
    session: AsyncSession

    async def now(self) -> datetime:
        return await SqlIdentityTransaction(self.session).now()

    async def policy_version(
        self, kind: PolicyKind, version: PolicyVersion
    ) -> PublishedPolicy | None:
        # Immutable version lookup deliberately includes a retained timestamp later
        # than now; a replay must never republish or invent another policy identity.
        row = await self.session.scalar(
            select(PolicyDocumentRecord).where(
                PolicyDocumentRecord.kind == kind.value,
                PolicyDocumentRecord.version == version.value,
            )
        )
        if row is None:
            return None
        return PublishedPolicy(
            PolicyReference(
                row.id, PolicyKind(row.kind), PolicyVersion(row.version), row.published_at
            ),
            row.title,
            row.content,
        )

    async def latest_reference(self, kind: PolicyKind) -> PolicyReference | None:
        row = await self.session.scalar(
            select(PolicyDocumentRecord)
            .where(PolicyDocumentRecord.kind == kind.value)
            .order_by(PolicyDocumentRecord.published_at.desc(), PolicyDocumentRecord.id.desc())
            .limit(1)
        )
        return (
            PolicyReference(
                row.id, PolicyKind(row.kind), PolicyVersion(row.version), row.published_at
            )
            if row is not None
            else None
        )

    async def add_policy(self, policy: PublishedPolicy) -> None:
        self.session.add(
            PolicyDocumentRecord(
                id=policy.reference.id,
                kind=policy.reference.kind.value,
                version=policy.reference.version.value,
                title=policy.title,
                content=policy.content,
                published_at=policy.reference.published_at,
            )
        )
        await self.session.flush()

    async def current_reference(self, kind: PolicyKind, at: datetime) -> PolicyReference | None:
        return await SqlRegistrationTransaction(self.session).current_reference(kind, at)

    async def manifest(self, version: str) -> CatalogueProvenance | None:
        row = await self.session.get(BootstrapCatalogueManifestRecord, version)
        return (
            CatalogueProvenance(
                row.version,
                row.sha256,
                row.canonical_json,
                row.applied_at,
                row.subject_count,
                row.alias_count,
            )
            if row is not None
            else None
        )

    async def subjects(
        self, identities: tuple[UUID, ...], names: tuple[str, ...]
    ) -> tuple[Subject, ...]:
        roots = tuple(
            await self.session.scalars(
                select(SubjectRecord).where(
                    or_(SubjectRecord.id.in_(identities), SubjectRecord.normalized_name.in_(names))
                )
            )
        )
        if not roots:
            return ()
        rows = await self.session.execute(
            select(SubjectAliasRecord.subject_id, SubjectAliasRecord.name)
            .where(SubjectAliasRecord.subject_id.in_(tuple(root.id for root in roots)))
            .order_by(SubjectAliasRecord.subject_id, SubjectAliasRecord.slot)
        )
        aliases: dict[UUID, list[str]] = {}
        for subject_id, name in rows:
            aliases.setdefault(subject_id, []).append(name)
        return tuple(
            Subject(
                row.id, row.name, tuple(aliases.get(row.id, ())), row.created_at, row.archived_at
            )
            for row in roots
        )

    async def add_subjects(self, subjects: tuple[Subject, ...]) -> None:
        if any(subject.archived_at is not None for subject in subjects):
            raise RuntimeError("Bootstrap can only create new unarchived subjects")
        self.session.add_all(
            [
                SubjectRecord(
                    id=subject.id,
                    name=subject.name,
                    normalized_name=subject_key(subject.name),
                    created_at=subject.created_at,
                    archived_at=None,
                )
                for subject in subjects
            ]
        )
        await self.session.flush()
        self.session.add_all(
            [
                SubjectAliasRecord(
                    subject_id=subject.id,
                    slot=slot,
                    name=alias,
                    normalized_alias=subject_key(alias),
                )
                for subject in subjects
                for slot, alias in enumerate(subject.aliases)
            ]
        )
        await self.session.flush()

    async def add_manifest(self, source: CatalogueProvenance) -> None:
        self.session.add(
            BootstrapCatalogueManifestRecord(
                version=source.version,
                sha256=source.sha256,
                canonical_json=source.canonical_json,
                applied_at=source.applied_at,
                subject_count=source.subject_count,
                alias_count=source.alias_count,
            )
        )
        await self.session.flush()


@dataclass(frozen=True, slots=True)
class SqlBootstrapDataUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlBootstrapDataTransaction]:
        async with open_transaction(self.sessions) as session:
            await session.execute(
                select(func.pg_advisory_xact_lock(BOOTSTRAP_LOCK_NAMESPACE, BOOTSTRAP_LOCK_KEY))
            )
            yield SqlBootstrapDataTransaction(session)
