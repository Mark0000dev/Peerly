from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from studymate.domain.media import PhotoRevision
from studymate.domain.operator.photo_review import (
    PhotoRecoveryState,
    PhotoReviewAction,
    PhotoReviewRevision,
    photo_review_recovery,
)


def requirement() -> PhotoReviewRevision:
    now = datetime.now(UTC)
    account_id = uuid4()
    return PhotoReviewRevision(
        uuid4(),
        account_id,
        1,
        None,
        PhotoReviewAction.REQUIRE_REPLACEMENT,
        PhotoRevision(account_id, 1, uuid4(), now),
        uuid4(),
        uuid4(),
        1,
        now,
        "Please upload a clear photo showing your face.",
    )


def test_human_approval_requires_new_published_photo_and_keeps_original_fact() -> None:
    original = requirement()
    approved = replace(
        original,
        id=uuid4(),
        version=2,
        previous_revision_id=original.id,
        action=PhotoReviewAction.APPROVE_REPLACEMENT,
        photo=replace(original.photo, version=2, upload_id=uuid4()),
    )
    original.validate_successor(approved)
    assert original.replacement_required
    assert not approved.replacement_required
    assert original.reason not in repr(original)


@pytest.mark.parametrize(
    "changed", ["same_upload", "same_version", "wrong_account", "wrong_parent", "past"]
)
def test_invalid_review_continuity_does_not_restore_exposure(changed: str) -> None:
    original = requirement()
    candidate = replace(
        original,
        id=uuid4(),
        version=2,
        previous_revision_id=original.id,
        action=PhotoReviewAction.APPROVE_REPLACEMENT,
        photo=replace(original.photo, version=2, upload_id=uuid4()),
    )
    if changed == "same_upload":
        candidate = replace(
            candidate, photo=replace(candidate.photo, upload_id=original.photo.upload_id)
        )
    elif changed == "same_version":
        candidate = replace(candidate, photo=replace(candidate.photo, version=1))
    elif changed == "wrong_account":
        other_id = uuid4()
        candidate = replace(
            candidate, account_id=other_id, photo=replace(candidate.photo, account_id=other_id)
        )
    elif changed == "wrong_parent":
        candidate = replace(candidate, previous_revision_id=uuid4())
    else:
        candidate = replace(
            candidate,
            photo=replace(candidate.photo, saved_at=original.decided_at - timedelta(seconds=2)),
            decided_at=original.decided_at - timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match=r"Photo review successor|Human approval"):
        original.validate_successor(candidate)


def test_approval_cannot_be_first_or_repeat_without_a_requirement() -> None:
    original = requirement()
    with pytest.raises(ValueError, match="Approval requires"):
        replace(original, action=PhotoReviewAction.APPROVE_REPLACEMENT)
    approved = replace(
        original,
        id=uuid4(),
        version=2,
        previous_revision_id=original.id,
        action=PhotoReviewAction.APPROVE_REPLACEMENT,
        photo=replace(original.photo, version=2, upload_id=uuid4()),
    )
    with pytest.raises(ValueError, match="Human approval"):
        approved.validate_successor(
            replace(approved, id=uuid4(), version=3, previous_revision_id=approved.id)
        )


def test_ordinary_photo_never_acquires_a_global_human_review_gate() -> None:
    source = requirement()
    assert photo_review_recovery(None, source.photo).state == PhotoRecoveryState.NOT_REQUIRED
    assert photo_review_recovery(None, None).version == 0


def test_new_ready_photo_remains_blocked_until_explicit_human_approval() -> None:
    source = requirement()
    replacement = replace(source.photo, version=2, upload_id=uuid4())
    assert (
        photo_review_recovery(source, source.photo).state == PhotoRecoveryState.REPLACEMENT_REQUIRED
    )
    assert (
        photo_review_recovery(source, replacement).state == PhotoRecoveryState.AWAITING_HUMAN_REVIEW
    )
    assert source.replacement_required
