"""Synthetic explicit imports against migrated PostgreSQL in disposable unique schemas."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.bootstrap_data.apply import (
    ApplyBootstrapData,
    BootstrapConflictCode,
    BootstrapConflictError,
    MissingPublishedPoliciesError,
)
from studymate.domain.bootstrap_data.inputs import BootstrapBatch
from studymate.domain.registration import PolicyVersion
from studymate.infrastructure.bootstrap_data.models import BootstrapCatalogueManifestRecord
from studymate.infrastructure.bootstrap_data.persistence import SqlBootstrapDataUnitOfWork
from studymate.infrastructure.persistence.catalogue_models import SubjectRecord
from studymate.infrastructure.persistence.registration_models import PolicyDocumentRecord
from tests.unit.bootstrap_data.data import batch

pytestmark = pytest.mark.integration


def use_case(engine: AsyncEngine) -> ApplyBootstrapData:
    return ApplyBootstrapData(
        SqlBootstrapDataUnitOfWork(async_sessionmaker(engine, expire_on_commit=False))
    )


async def counts(engine: AsyncEngine) -> tuple[int, int, int]:
    async with async_sessionmaker(engine)() as session:
        return (
            await session.scalar(select(func.count()).select_from(PolicyDocumentRecord)) or 0,
            await session.scalar(select(func.count()).select_from(SubjectRecord)) or 0,
            await session.scalar(select(func.count()).select_from(BootstrapCatalogueManifestRecord))
            or 0,
        )


async def test_atomic_initial_import_and_retained_exact_replay(
    identity_engine: AsyncEngine,
) -> None:
    apply = use_case(identity_engine)
    first = await apply(batch())
    replay = await apply(batch())
    assert first.policies_created == len(batch().policies)
    assert replay.policies_created == 0
    assert replay.terms == first.terms
    assert replay.privacy == first.privacy
    assert replay.catalogue.replayed
    assert await counts(identity_engine) == (2, 1, 1)
    async with async_sessionmaker(identity_engine)() as session:
        manifest = await session.get(BootstrapCatalogueManifestRecord, "test-v1")
        assert manifest is not None
        source = batch().catalogue
        assert source is not None
        assert manifest.sha256 == source.sha256
        assert manifest.canonical_json == source.canonical_json
        policy = await session.get(PolicyDocumentRecord, first.terms.id)
        assert policy is not None
        assert policy.content == batch().policies[0].content


async def test_missing_pair_rolls_back_every_table(identity_engine: AsyncEngine) -> None:
    original = batch()
    with pytest.raises(MissingPublishedPoliciesError):
        await use_case(identity_engine)(replace(original, policies=original.policies[:1]))
    assert await counts(identity_engine) == (0, 0, 0)


async def test_same_input_concurrently_commits_once(identity_engine: AsyncEngine) -> None:
    apply = use_case(identity_engine)
    results = await asyncio.gather(apply(batch()), apply(batch()))
    assert sorted(result.policies_created for result in results) == [0, 2]
    assert results[0].terms == results[1].terms
    assert results[0].privacy == results[1].privacy
    assert sum(result.catalogue.created for result in results) == 1
    assert await counts(identity_engine) == (2, 1, 1)


async def test_conflicting_concurrent_policy_payload_has_single_winner(
    identity_engine: AsyncEngine,
) -> None:
    original = batch()
    altered = replace(
        original,
        policies=(
            replace(original.policies[0], content="Other synthetic body"),
            original.policies[1],
        ),
    )
    apply = use_case(identity_engine)

    async def attempt(value: BootstrapBatch) -> BootstrapConflictCode | None:
        try:
            await apply(value)
        except BootstrapConflictError as error:
            return error.code
        return None

    results = await asyncio.gather(attempt(original), attempt(altered))
    assert results.count(None) == 1
    assert results.count(BootstrapConflictCode.POLICY_VERSION) == 1
    assert await counts(identity_engine) == (2, 1, 1)


async def test_older_replay_returns_actual_new_current_reference(
    identity_engine: AsyncEngine,
) -> None:
    apply = use_case(identity_engine)
    first = await apply(batch())
    newer = replace(batch().policies[0], version=PolicyVersion("test-v2"))
    second = await apply(BootstrapBatch((newer,), None))
    replay = await apply(batch())
    assert second.terms.id != first.terms.id
    assert replay.terms == second.terms
    assert replay.privacy == first.privacy
    async with async_sessionmaker(identity_engine)() as session:
        old = await session.get(PolicyDocumentRecord, first.terms.id)
        assert old is not None
        assert old.published_at == first.terms.published_at
    assert await counts(identity_engine) == (3, 1, 1)


async def test_future_retained_version_is_not_claimed_published(
    identity_engine: AsyncEngine,
) -> None:
    apply = use_case(identity_engine)
    await apply(batch())
    future = replace(batch().policies[0], version=PolicyVersion("future"))
    async with SqlBootstrapDataUnitOfWork(async_sessionmaker(identity_engine)).transaction() as tx:
        future_policy = future.publish(UUID(int=999), (await tx.now()) + timedelta(days=1))
        await tx.add_policy(future_policy)
    with pytest.raises(BootstrapConflictError) as error:
        await apply(BootstrapBatch((future,), None))
    assert error.value.code == BootstrapConflictCode.POLICY_PUBLICATION
    assert await counts(identity_engine) == (3, 1, 1)
    async with async_sessionmaker(identity_engine)() as session:
        retained = await session.get(PolicyDocumentRecord, future_policy.reference.id)
        assert retained is not None
        assert retained.published_at == future_policy.reference.published_at


async def test_catalogue_conflict_rolls_back_new_policy(identity_engine: AsyncEngine) -> None:
    apply = use_case(identity_engine)
    first = await apply(batch())
    source = batch().catalogue
    assert source is not None
    changed = replace(source, subjects=(replace(source.subjects[0], aliases=()),))
    newer = replace(batch().policies[0], version=PolicyVersion("test-v2"))
    with pytest.raises(BootstrapConflictError):
        await apply(BootstrapBatch((newer,), changed))
    replay = await apply(batch())
    assert replay.terms == first.terms
    assert await counts(identity_engine) == (2, 1, 1)


async def test_archived_and_omitted_catalogue_rows_remain_untouched(
    identity_engine: AsyncEngine,
) -> None:
    apply = use_case(identity_engine)
    await apply(batch())
    source = batch().catalogue
    assert source is not None
    authored = source.subjects[0]
    async with async_sessionmaker(identity_engine).begin() as session:
        row = await session.get(SubjectRecord, authored.id)
        assert row is not None
        archived_at = row.created_at + timedelta(seconds=1)
        row.archived_at = archived_at
    added = replace(authored, id=UUID(int=201), name="Another Synthetic Subject", aliases=())
    await apply(BootstrapBatch((), replace(source, version="v2", subjects=(added,))))
    await apply(BootstrapBatch((), replace(source, version="v3")))
    async with async_sessionmaker(identity_engine)() as session:
        retained = await session.get(SubjectRecord, authored.id)
        assert retained is not None
        assert retained.archived_at == archived_at
    assert await counts(identity_engine) == (2, 2, 3)


@pytest.mark.parametrize("change", ["name_owner", "aliases"])
async def test_catalogue_existing_identity_and_normalized_name_are_immutable(
    identity_engine: AsyncEngine, change: str
) -> None:
    apply = use_case(identity_engine)
    await apply(batch())
    source = batch().catalogue
    assert source is not None
    authored = source.subjects[0]
    if change == "name_owner":
        authored = replace(authored, id=UUID(int=201), name=" synthetic subject ")
        expected = BootstrapConflictCode.SUBJECT_NAME
    else:
        authored = replace(authored, aliases=())
        expected = BootstrapConflictCode.SUBJECT_IDENTITY
    with pytest.raises(BootstrapConflictError) as caught:
        await apply(BootstrapBatch((), replace(source, version="v2", subjects=(authored,))))
    assert caught.value.code == expected
    assert await counts(identity_engine) == (2, 1, 1)
