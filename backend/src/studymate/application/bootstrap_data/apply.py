"""Immutable policy publication and append/unchanged catalogue import in one transaction."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from studymate.application.bootstrap_data.ports import (
    BootstrapDataTransaction,
    BootstrapDataUnitOfWork,
)
from studymate.domain.bootstrap_data.inputs import (
    BootstrapBatch,
    CatalogueManifest,
    CatalogueProvenance,
)
from studymate.domain.catalogue import Subject, subject_key
from studymate.domain.registration import PolicyKind, PolicyReference


class BootstrapConflictCode(StrEnum):
    POLICY_PUBLICATION = "policy_publication_conflict"
    POLICY_VERSION = "policy_version_conflict"
    SUBJECT_IDENTITY = "subject_identity_conflict"
    SUBJECT_NAME = "subject_name_conflict"
    MANIFEST_VERSION = "manifest_version_conflict"
    MANIFEST_DRIFT = "manifest_data_conflict"


class BootstrapConflictError(Exception):
    def __init__(self, code: BootstrapConflictCode, resource_id: UUID | None = None) -> None:
        super().__init__(code.value)
        self.code, self.resource_id = code, resource_id


class MissingPublishedPoliciesError(Exception):
    """After application both actually current Terms and Privacy must exist."""


@dataclass(frozen=True, slots=True)
class CatalogueApplied:
    created: int = 0
    unchanged: int = 0
    version: str | None = None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class BootstrapApplied:
    policies_created: int
    policies_unchanged: int
    catalogue: CatalogueApplied
    terms: PolicyReference
    privacy: PolicyReference


async def apply_catalogue(
    tx: BootstrapDataTransaction, manifest: CatalogueManifest
) -> CatalogueApplied:
    prior = await tx.manifest(manifest.version)
    if prior is not None and prior.version != manifest.version:
        raise RuntimeError("Manifest lookup differs from the requested explicit version")
    if prior is not None and (
        prior.sha256 != manifest.sha256 or prior.canonical_json != manifest.canonical_json
    ):
        raise BootstrapConflictError(BootstrapConflictCode.MANIFEST_VERSION)
    values = await tx.subjects(
        tuple(subject.id for subject in manifest.subjects),
        tuple(subject_key(subject.name) for subject in manifest.subjects),
    )
    by_id = {subject.id: subject for subject in values}
    by_name = {subject_key(subject.name): subject for subject in values}
    if len(by_id) != len(values) or len(by_name) != len(values):
        raise RuntimeError("Catalogue source returned ambiguous actual identities")
    created: list[Subject] = []
    unchanged = 0
    at = await tx.now()
    for authored in manifest.subjects:
        current = by_id.get(authored.id)
        if current is not None:
            if (current.name, current.aliases) != (authored.name, authored.aliases):
                raise BootstrapConflictError(BootstrapConflictCode.SUBJECT_IDENTITY, authored.id)
            unchanged += 1
        elif subject_key(authored.name) in by_name:
            raise BootstrapConflictError(BootstrapConflictCode.SUBJECT_NAME, authored.id)
        elif prior is not None:
            raise BootstrapConflictError(BootstrapConflictCode.MANIFEST_DRIFT, authored.id)
        else:
            created.append(authored.create(at))
    if prior is not None:
        return CatalogueApplied(0, unchanged, prior.version, True)
    await tx.add_subjects(tuple(created))
    await tx.add_manifest(
        CatalogueProvenance(
            manifest.version,
            manifest.sha256,
            manifest.canonical_json,
            at,
            len(manifest.subjects),
            manifest.alias_count,
        )
    )
    return CatalogueApplied(len(created), unchanged, manifest.version, False)


@dataclass(frozen=True, slots=True)
class ApplyBootstrapData:
    unit_of_work: BootstrapDataUnitOfWork

    async def __call__(self, batch: BootstrapBatch) -> BootstrapApplied:
        async with self.unit_of_work.transaction() as tx:
            created = 0
            unchanged = 0
            at = await tx.now()
            for draft in batch.policies:
                current = await tx.policy_version(draft.kind, draft.version)
                if current is not None:
                    if (current.reference.kind, current.reference.version) != (
                        draft.kind,
                        draft.version,
                    ):
                        raise RuntimeError("Policy lookup differs from requested immutable version")
                    if (current.title, current.content) != (draft.title, draft.content):
                        raise BootstrapConflictError(
                            BootstrapConflictCode.POLICY_VERSION, current.reference.id
                        )
                    if current.reference.published_at > at:
                        raise BootstrapConflictError(
                            BootstrapConflictCode.POLICY_PUBLICATION, current.reference.id
                        )
                    unchanged += 1
                else:
                    latest = await tx.latest_reference(draft.kind)
                    if latest is not None and latest.published_at >= at:
                        raise BootstrapConflictError(
                            BootstrapConflictCode.POLICY_PUBLICATION, latest.id
                        )
                    await tx.add_policy(draft.publish(uuid4(), at))
                    created += 1
            catalogue = (
                await apply_catalogue(tx, batch.catalogue)
                if batch.catalogue is not None
                else CatalogueApplied()
            )
            current_at = await tx.now()
            terms = await tx.current_reference(PolicyKind.TERMS, current_at)
            privacy = await tx.current_reference(PolicyKind.PRIVACY, current_at)
            if terms is None or privacy is None:
                raise MissingPublishedPoliciesError
            if terms.kind != PolicyKind.TERMS or privacy.kind != PolicyKind.PRIVACY:
                raise RuntimeError("Current policy references lost their actual document kinds")
            return BootstrapApplied(created, unchanged, catalogue, terms, privacy)
