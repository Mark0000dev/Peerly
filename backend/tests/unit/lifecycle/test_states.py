from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.domain.lifecycle.states import (
    MAX_LIFECYCLE_REASON_CHARACTERS,
    MAX_LIFECYCLE_SOURCE_VERSION,
    AccountLifecycle,
    BanChangeEvidence,
    BanRevision,
    BanTransition,
    DeletedLifecycleAccountError,
    DeletionRevision,
    DeletionTransition,
    LifecycleOperation,
    LifecycleReason,
    changed_ban_state,
    changed_deletion_state,
    plan_ban_change,
    plan_deletion,
)
from studymate.domain.operator.access import OperatorAccess
from tests.unit.identity_store import NOW

ACCOUNT = UUID(int=201)
ACTOR = UUID(int=202)
SESSION = UUID(int=203)
WORKFLOW = UUID(int=204)
REASON = "  Private original lifecycle reason\n  preserved spacing  "


def access() -> OperatorAccess:
    return OperatorAccess(ACTOR, 1, True, NOW - timedelta(days=1))


def evidence() -> BanChangeEvidence:
    return BanChangeEvidence(uuid4(), NOW, access(), SESSION)


def ban_revision(*, banned: bool = True, version: int = 1) -> BanRevision:
    return BanRevision(
        uuid4(), ACCOUNT, version, banned, NOW, access(), SESSION, LifecycleReason(REASON)
    )


def deletion_revision(version: int = 1) -> DeletionRevision:
    return DeletionRevision(uuid4(), ACCOUNT, version, NOW, SESSION, WORKFLOW)


@pytest.mark.parametrize("banned", [False, True])
@pytest.mark.parametrize("deleted", [False, True])
def test_lifecycle_flags_are_independent_and_legacy_has_no_invented_source(
    banned: bool, deleted: bool
) -> None:
    state = AccountLifecycle(ACCOUNT, NOW if banned else None, NOW if deleted else None)
    assert state.source_version == 0
    assert state.account_allows_student_actions == (not banned and not deleted)
    assert state.next_source_version() == 1
    assert not hasattr(state, "operator_id")
    assert not hasattr(state, "reason")


def test_ban_actual_source_and_exact_reason_no_private_repr() -> None:
    state = AccountLifecycle(ACCOUNT)
    proof = evidence()
    planned = plan_ban_change(state, banned=True, evidence=proof, reason=LifecycleReason(REASON))
    assert planned.changed
    assert planned.before == state
    assert planned.after.banned_at == NOW
    assert planned.after.deleted_at is None
    assert planned.after.source_version == state.next_source_version()
    source = planned.revision
    assert source is not None
    assert source.id == proof.id
    assert source.operator_access == access()
    assert source.actor_session_id == SESSION
    assert source.reason.value == REASON
    assert source.operation == LifecycleOperation.BAN
    assert REASON not in repr(source)
    assert REASON not in repr(planned)
    assert REASON not in repr(source.reason)
    assert not planned.after.account_allows_student_actions


def test_unban_preserves_deletion_and_other_source_history() -> None:
    state = AccountLifecycle(ACCOUNT, NOW - timedelta(days=2), NOW - timedelta(days=1), 2)
    result = plan_ban_change(
        state, banned=False, evidence=evidence(), reason=LifecycleReason(REASON)
    )
    assert result.changed
    assert result.after.banned_at is None
    assert result.after.deleted_at == state.deleted_at
    assert result.after.source_version == state.source_version + 1
    assert not result.after.account_allows_student_actions
    assert result.revision is not None
    assert result.revision.operation == LifecycleOperation.UNBAN
    assert result.before == state


@pytest.mark.parametrize("banned", [True, False])
def test_noop_never_creates_revision_even_legacy_or_exhausted_version(banned: bool) -> None:
    for version in (0, MAX_LIFECYCLE_SOURCE_VERSION):
        state = AccountLifecycle(ACCOUNT, NOW if banned else None, source_version=version)
        result = plan_ban_change(
            state, banned=banned, evidence=evidence(), reason=LifecycleReason(REASON)
        )
        assert not result.changed
        assert result.revision is None
        assert result.before == state
        assert result.after is state


@pytest.mark.parametrize("banned", [False, True])
def test_soft_deletion_retains_ban_and_original_identity_without_restore(banned: bool) -> None:
    state = AccountLifecycle(ACCOUNT, NOW - timedelta(days=1) if banned else None)
    result = plan_deletion(
        state, change_id=uuid4(), at=NOW, actor_session_id=SESSION, workflow_id=WORKFLOW
    )
    assert result.after.account_id == ACCOUNT
    assert result.after.banned_at == state.banned_at
    assert result.after.deleted_at == NOW
    assert result.after.source_version == state.next_source_version()
    assert result.revision.actor_session_id == SESSION
    assert result.revision.workflow_id == WORKFLOW
    assert result.revision.operation == LifecycleOperation.DELETE
    assert not result.after.account_allows_student_actions
    with pytest.raises(DeletedLifecycleAccountError):
        plan_deletion(
            result.after, change_id=uuid4(), at=NOW, actor_session_id=SESSION, workflow_id=WORKFLOW
        )
    assert not hasattr(result, "purged")
    assert not hasattr(result, "restored")


@pytest.mark.parametrize("version", [-1, True, MAX_LIFECYCLE_SOURCE_VERSION + 1])
def test_actual_source_version_bounds(version: int) -> None:
    with pytest.raises(ValueError, match="retained source version"):
        AccountLifecycle(ACCOUNT, source_version=version)
    with pytest.raises(ValueError, match="positive bounded"):
        ban_revision(version=version)
    with pytest.raises(ValueError, match="positive bounded"):
        deletion_revision(version)


def test_zero_source_and_exhaustion_cannot_be_new_immutable_revisions() -> None:
    with pytest.raises(ValueError, match="positive bounded"):
        ban_revision(version=0)
    with pytest.raises(ValueError, match="positive bounded"):
        deletion_revision(0)
    state = AccountLifecycle(ACCOUNT, source_version=MAX_LIFECYCLE_SOURCE_VERSION)
    with pytest.raises(ValueError, match="exhausted"):
        state.next_source_version()


@pytest.mark.parametrize("reason", ["", "  \n ", "x" * (MAX_LIFECYCLE_REASON_CHARACTERS + 1)])
def test_private_reason_bounded_without_normalizing(reason: str) -> None:
    with pytest.raises(ValueError, match="bounded nonblank"):
        LifecycleReason(reason)


def test_reason_counts_unicode_characters_and_preserves_exact_whitespace() -> None:
    value = "あ" * MAX_LIFECYCLE_REASON_CHARACTERS
    assert LifecycleReason(value).value == value
    assert LifecycleReason(REASON).value == REASON


def test_recorded_grant_must_be_active_at_actual_change_time() -> None:
    with pytest.raises(ValueError, match="actual active operator grant"):
        replace(evidence(), operator_access=replace(access(), active=False))
    with pytest.raises(ValueError, match="actual active operator grant"):
        replace(
            ban_revision(), operator_access=replace(access(), changed_at=NOW + timedelta(seconds=1))
        )


def test_real_account_version_time_and_noop_source_invariants() -> None:
    state = AccountLifecycle(ACCOUNT)
    with pytest.raises(ValueError, match="account or next source version"):
        changed_ban_state(state, replace(ban_revision(), account_id=uuid4()))
    with pytest.raises(ValueError, match="account or next source version"):
        changed_ban_state(state, ban_revision(version=2))
    with pytest.raises(ValueError, match="No-op ban"):
        changed_ban_state(state, ban_revision(banned=False))
    with pytest.raises(ValueError, match="precede"):
        changed_ban_state(
            AccountLifecycle(ACCOUNT, NOW + timedelta(seconds=1)), ban_revision(banned=False)
        )
    with pytest.raises(ValueError, match="account or next source version"):
        changed_deletion_state(state, replace(deletion_revision(), account_id=uuid4()))
    with pytest.raises(ValueError, match="account or next source version"):
        changed_deletion_state(state, deletion_revision(2))
    with pytest.raises(ValueError, match="precede"):
        changed_deletion_state(
            AccountLifecycle(ACCOUNT, NOW + timedelta(seconds=1)), deletion_revision()
        )
    with pytest.raises(ValueError, match="No-op ban"):
        BanTransition(state, replace(state, source_version=1), None)
    with pytest.raises(ValueError, match="actual immutable source"):
        BanTransition(state, state, ban_revision())
    with pytest.raises(ValueError, match="actual immutable source"):
        DeletionTransition(state, state, deletion_revision())


def test_naive_times_cannot_enter_retained_lifecycle_sources() -> None:
    naive = NOW.replace(tzinfo=None)
    with pytest.raises(ValueError, match="timezone"):
        AccountLifecycle(ACCOUNT, banned_at=naive)
    with pytest.raises(ValueError, match="timezone"):
        AccountLifecycle(ACCOUNT, deleted_at=naive)
    with pytest.raises(ValueError, match="timezone"):
        replace(evidence(), at=naive)
    with pytest.raises(ValueError, match="timezone"):
        replace(ban_revision(), changed_at=naive)
    with pytest.raises(ValueError, match="timezone"):
        replace(deletion_revision(), deleted_at=naive)


@pytest.mark.parametrize("value", ["\x00", "private\x00reason", "\ud800", "private\x01reason"])
def test_reason_rejects_existing_unsupported_plain_text_controls(value: str) -> None:
    with pytest.raises(ValueError, match="unsupported control"):
        LifecycleReason(value)
