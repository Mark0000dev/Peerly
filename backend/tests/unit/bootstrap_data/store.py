"""Typed transaction fake, not PostgreSQL persistence or a bundled reference-data seed."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Self
from uuid import UUID

from studymate.domain.bootstrap_data.inputs import CatalogueProvenance
from studymate.domain.catalogue import Subject, subject_key
from studymate.domain.registration import (
    PolicyKind,
    PolicyReference,
    PolicyVersion,
    PublishedPolicy,
)
from tests.unit.identity_store import NOW


class Store:
    def __init__(self) -> None:
        self.clock = NOW
        self.policies: dict[tuple[PolicyKind, PolicyVersion], PublishedPolicy] = {}
        self.catalogue: dict[UUID, Subject] = {}
        self.manifests: dict[str, CatalogueProvenance] = {}
        self.fail_after_manifest = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Self]:
        before = self.policies.copy(), self.catalogue.copy(), self.manifests.copy()
        try:
            yield self
        except BaseException:
            self.policies, self.catalogue, self.manifests = before
            raise

    async def now(self) -> datetime:
        return self.clock

    async def policy_version(
        self, kind: PolicyKind, version: PolicyVersion
    ) -> PublishedPolicy | None:
        return self.policies.get((kind, version))

    async def latest_reference(self, kind: PolicyKind) -> PolicyReference | None:
        values = tuple(p.reference for p in self.policies.values() if p.reference.kind == kind)
        return max(values, key=lambda value: (value.published_at, value.id.int)) if values else None

    async def add_policy(self, policy: PublishedPolicy) -> None:
        self.policies[policy.reference.kind, policy.reference.version] = policy

    async def current_reference(self, kind: PolicyKind, at: datetime) -> PolicyReference | None:
        values = tuple(
            policy.reference
            for policy in self.policies.values()
            if policy.reference.kind == kind and policy.reference.published_at <= at
        )
        return max(values, key=lambda value: (value.published_at, value.id.int)) if values else None

    async def manifest(self, version: str) -> CatalogueProvenance | None:
        return self.manifests.get(version)

    async def subjects(
        self, identities: tuple[UUID, ...], names: tuple[str, ...]
    ) -> tuple[Subject, ...]:
        return tuple(
            subject
            for subject in self.catalogue.values()
            if subject.id in identities or subject_key(subject.name) in names
        )

    async def add_subjects(self, subjects: tuple[Subject, ...]) -> None:
        self.catalogue.update((subject.id, subject) for subject in subjects)

    async def add_manifest(self, source: CatalogueProvenance) -> None:
        self.manifests[source.version] = source
        if self.fail_after_manifest:
            raise RuntimeError("synthetic transaction failure")
