from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest

from studymate.application.bootstrap_data.apply import (
    ApplyBootstrapData,
    BootstrapConflictCode,
    BootstrapConflictError,
    MissingPublishedPoliciesError,
)
from studymate.domain.bootstrap_data.inputs import BootstrapBatch, CatalogueManifest
from studymate.domain.registration import PolicyVersion
from tests.unit.bootstrap_data.data import batch
from tests.unit.bootstrap_data.store import Store


async def test_initial_explicit_pair_catalogue_and_exact_replay_preserve_source_ids_and_times() -> (
    None
):
    store = Store()
    input_batch = batch()
    first = await ApplyBootstrapData(store)(input_batch)
    policies, subjects, manifests = (
        store.policies.copy(),
        store.catalogue.copy(),
        store.manifests.copy(),
    )
    store.clock += timedelta(hours=1)
    replay = await ApplyBootstrapData(store)(input_batch)
    assert first.policies_created == len(input_batch.policies)
    assert replay.policies_created == 0
    assert replay.policies_unchanged == len(input_batch.policies)
    assert replay.catalogue.replayed
    assert store.policies == policies
    assert store.catalogue == subjects
    assert store.manifests == manifests
    assert replay.terms == first.terms
    assert replay.privacy == first.privacy


async def test_missing_initial_policy_pair_rolls_back_catalogue_manifest_and_single_policy() -> (
    None
):
    store = Store()
    original = batch()
    with pytest.raises(MissingPublishedPoliciesError):
        await ApplyBootstrapData(store)(replace(original, policies=original.policies[:1]))
    assert not store.policies
    assert not store.catalogue
    assert not store.manifests


async def test_same_policy_version_content_cannot_be_changed_or_republished() -> None:
    store = Store()
    original = batch()
    await ApplyBootstrapData(store)(original)
    altered = replace(original, policies=(replace(original.policies[0], content="Changed body"),))
    with pytest.raises(BootstrapConflictError) as error:
        await ApplyBootstrapData(store)(altered)
    assert error.value.code == BootstrapConflictCode.POLICY_VERSION
    assert "Changed body" not in str(error.value)


async def test_new_version_publishes_now_without_overwriting_older_policy_source() -> None:
    store = Store()
    original = batch()
    first = await ApplyBootstrapData(store)(original)
    store.clock += timedelta(hours=1)
    newer = replace(
        original.policies[0], version=PolicyVersion("test-v2"), content="New actual authored body"
    )
    result = await ApplyBootstrapData(store)(BootstrapBatch((newer,), None))
    assert result.terms.id != first.terms.id
    assert result.terms.published_at == store.clock
    assert result.privacy == first.privacy
    assert len(store.policies) == len(original.policies) + 1


@pytest.mark.parametrize("fault", ["name", "aliases", "same_version", "other_id"])
async def test_catalogue_conflicts_are_not_renames_alias_edits_or_id_remapping(fault: str) -> None:
    store = Store()
    original = batch()
    await ApplyBootstrapData(store)(original)
    assert original.catalogue is not None
    subject = original.catalogue.subjects[0]
    if fault == "name":
        subject = replace(subject, name="Renamed subject")
    elif fault == "aliases":
        subject = replace(subject, aliases=())
    else:
        subject = replace(subject, id=UUID(int=201))
    version = original.catalogue.version if fault == "same_version" else "test-v2"
    changed = BootstrapBatch((), CatalogueManifest(version, (subject,)))
    with pytest.raises(BootstrapConflictError):
        await ApplyBootstrapData(store)(changed)
    assert len(store.catalogue) == 1
    assert len(store.manifests) == 1


async def test_new_manifest_omission_preserves_old_rows_and_archived_source_never_reactivates() -> (
    None
):
    store = Store()
    original = batch()
    await ApplyBootstrapData(store)(original)
    assert original.catalogue is not None
    authored = original.catalogue.subjects[0]
    store.clock += timedelta(hours=1)
    store.catalogue[authored.id] = replace(store.catalogue[authored.id], archived_at=store.clock)
    added = replace(authored, id=UUID(int=201), name="Another Synthetic Subject", aliases=())
    await ApplyBootstrapData(store)(BootstrapBatch((), CatalogueManifest("test-v2", (added,))))
    assert set(store.catalogue) == {authored.id, added.id}
    await ApplyBootstrapData(store)(BootstrapBatch((), CatalogueManifest("test-v3", (authored,))))
    assert store.catalogue[authored.id].archived_at == store.clock


async def test_replayed_manifest_detects_missing_data_without_recreating_history() -> None:
    store = Store()
    original = batch()
    await ApplyBootstrapData(store)(original)
    store.catalogue.clear()
    with pytest.raises(BootstrapConflictError) as caught:
        await ApplyBootstrapData(store)(original)
    assert caught.value.code == BootstrapConflictCode.MANIFEST_DRIFT
    assert not store.catalogue


async def test_manifest_write_failure_rolls_back_all_new_reference_data() -> None:
    store = Store()
    store.fail_after_manifest = True
    with pytest.raises(RuntimeError, match="synthetic transaction"):
        await ApplyBootstrapData(store)(batch())
    assert not store.policies
    assert not store.catalogue
    assert not store.manifests


async def test_older_replay_preserves_new_current_pair_and_all_history() -> None:
    store = Store()
    original = batch()
    first = await ApplyBootstrapData(store)(original)
    store.clock += timedelta(hours=1)
    newer = replace(original.policies[0], version=PolicyVersion("test-v2"))
    second = await ApplyBootstrapData(store)(BootstrapBatch((newer,), None))
    history = store.policies.copy()
    replay = await ApplyBootstrapData(store)(original)
    assert replay.terms == second.terms
    assert replay.privacy == first.privacy
    assert store.policies == history


@pytest.mark.parametrize("offset", [-1, 0, 1])
async def test_new_publication_rejects_clock_behind_or_tied_with_latest(offset: int) -> None:
    store = Store()
    original = batch()
    await ApplyBootstrapData(store)(original)
    history = store.policies.copy()
    # Latest retained publication can be future-dated; it must not be bypassed.
    store.clock += timedelta(seconds=offset)
    if offset > 0:
        policy = original.policies[0].publish(UUID(int=999), store.clock + timedelta(hours=1))
        store.policies[policy.reference.kind, policy.reference.version] = policy
        history = store.policies.copy()
    newer = replace(original.policies[0], version=PolicyVersion("test-v2"))
    with pytest.raises(BootstrapConflictError) as caught:
        await ApplyBootstrapData(store)(BootstrapBatch((newer,), None))
    assert caught.value.code == BootstrapConflictCode.POLICY_PUBLICATION
    assert store.policies == history


async def test_requested_future_version_is_not_claimed_published_despite_current_pair() -> None:
    store = Store()
    original = batch()
    await ApplyBootstrapData(store)(original)
    future = replace(original.policies[0], version=PolicyVersion("future"))
    policy = future.publish(UUID(int=999), store.clock + timedelta(days=1))
    store.policies[policy.reference.kind, policy.reference.version] = policy
    history = store.policies.copy()
    with pytest.raises(BootstrapConflictError) as caught:
        await ApplyBootstrapData(store)(BootstrapBatch((future,), None))
    assert caught.value.code == BootstrapConflictCode.POLICY_PUBLICATION
    assert store.policies == history
