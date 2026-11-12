import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from deployment.backend.canonical_backfill import (
    BackfillRejectedError,
    CanonicalRef,
    Manifest,
    Plan,
    bind_intent,
    existing_intent,
    helper_digest,
    manifest_digest,
    read_plan,
    validate_plan,
)
from pydantic import ValidationError

from studymate.application.external_delivery.maintenance import BACKFILL_BATCH
from studymate.domain.operator.timeline import OperatorEventKind

NOW = datetime(2026, 11, 12, tzinfo=UTC)


def approved_plan(sources: tuple[CanonicalRef, ...] | None = None) -> Plan:
    manifest = Manifest(
        operation_id=uuid4(),
        performed_by="controlled-operator",
        cutoff=NOW,
        planned_at=NOW + timedelta(seconds=1),
        helper_sha256=helper_digest(),
        more=False,
        sources=sources
        if sources is not None
        else (
            CanonicalRef(
                id=UUID(int=1),
                kind=OperatorEventKind.EMAIL_CONFIRMED,
                occurred_at=NOW - timedelta(days=1),
            ),
        ),
    )
    return Plan(manifest=manifest, manifest_sha256=manifest_digest(manifest))


def test_explicit_selection_survives_json_roundtrip_without_actor_or_content() -> None:
    plan = approved_plan()
    restored = Plan.model_validate_json(plan.model_dump_json())
    validate_plan(restored)
    assert restored == plan
    source = restored.manifest.sources[0].model_dump(mode="json")
    assert set(source) == {"id", "kind", "occurred_at"}


@pytest.mark.parametrize(
    "fault", ["changed_cutoff", "helper_revision", "duplicate", "future", "naive"]
)
def test_changed_or_unrepresentable_selection_is_rejected(fault: str) -> None:
    original = approved_plan()
    manifest = original.manifest
    if fault == "changed_cutoff":
        manifest = manifest.model_copy(update={"cutoff": NOW - timedelta(seconds=1)})
        plan = original.model_copy(update={"manifest": manifest})
    else:
        if fault == "helper_revision":
            manifest = manifest.model_copy(update={"helper_sha256": "0" * 64})
        elif fault == "duplicate":
            manifest = manifest.model_copy(update={"sources": manifest.sources * 2})
        elif fault == "future":
            manifest = manifest.model_copy(update={"cutoff": NOW + timedelta(days=1)})
        else:
            manifest = manifest.model_copy(update={"cutoff": NOW.replace(tzinfo=None)})
        plan = Plan(manifest=manifest, manifest_sha256=manifest_digest(manifest))
    with pytest.raises(BackfillRejectedError):
        validate_plan(plan)


def test_more_than_actual_batch_bound_is_rejected_before_database() -> None:
    refs = tuple(
        CanonicalRef(id=UUID(int=index), kind=OperatorEventKind.EMAIL_CONFIRMED, occurred_at=NOW)
        for index in range(1, BACKFILL_BATCH + 2)
    )
    with pytest.raises(ValidationError):
        approved_plan(refs)


def test_source_after_cutoff_cannot_be_smuggled_in_with_fresh_digest() -> None:
    ref = CanonicalRef(
        id=UUID(int=1),
        kind=OperatorEventKind.EMAIL_CONFIRMED,
        occurred_at=NOW + timedelta(seconds=1),
    )
    with pytest.raises(BackfillRejectedError, match="source_after_cutoff"):
        validate_plan(approved_plan((ref,)))


def test_journal_replay_returns_original_exact_intent(tmp_path: Path) -> None:
    plan = approved_plan()
    bind_intent(tmp_path, plan)
    first = (tmp_path / (plan.manifest.operation_id.hex + ".json")).read_bytes()
    bind_intent(tmp_path, plan)
    assert existing_intent(tmp_path, plan.manifest.operation_id) == plan
    assert (tmp_path / (plan.manifest.operation_id.hex + ".json")).read_bytes() == first
    assert len(tuple(tmp_path.iterdir())) == 1


def test_same_operation_cannot_rebind_to_new_selected_ids(tmp_path: Path) -> None:
    original = approved_plan()
    bind_intent(tmp_path, original)
    changed_ref = original.manifest.sources[0].model_copy(update={"id": UUID(int=2)})
    changed_manifest = original.manifest.model_copy(update={"sources": (changed_ref,)})
    changed = Plan(manifest=changed_manifest, manifest_sha256=manifest_digest(changed_manifest))
    with pytest.raises(BackfillRejectedError, match="operation_intent_rebind"):
        bind_intent(tmp_path, changed)
    assert existing_intent(tmp_path, original.manifest.operation_id) == original


def test_unsafe_journal_permissions_and_symlink_are_not_followed(tmp_path: Path) -> None:
    journal = tmp_path / "journal"
    journal.mkdir(mode=0o755)
    journal.chmod(0o755)
    with pytest.raises(BackfillRejectedError, match="unsafe_journal_directory"):
        bind_intent(journal, approved_plan())
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(NotADirectoryError):
        bind_intent(alias, approved_plan())


def test_private_plan_rejects_group_readable_input(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(approved_plan().model_dump_json())
    path.chmod(0o640)
    with pytest.raises(BackfillRejectedError, match="unsafe_plan_file"):
        read_plan(path)


def test_canonical_only_manifest_rejects_extra_support_or_token_fields() -> None:
    plan = approved_plan()
    document: dict[str, object] = json.loads(plan.model_dump_json())
    document["support_case_ids"] = [str(uuid4())]
    with pytest.raises(ValidationError):
        Plan.model_validate_json(json.dumps(document))


def test_empty_terminal_plan_is_explicit_not_an_automatic_apply_loop() -> None:
    plan = approved_plan(())
    validate_plan(plan)
    assert plan.manifest.sources == ()
    assert not plan.manifest.more
