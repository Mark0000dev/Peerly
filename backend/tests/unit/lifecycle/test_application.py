from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.lifecycle.commands import (
    ChangeAccountBanCommand,
    DeleteOwnAccountCommand,
)
from studymate.application.lifecycle.intents import (
    LifecycleIntent,
    resolve_ban_intent,
    resolve_deletion_intent,
)
from studymate.application.lifecycle.planning import (
    check_submission_session_deadline,
    prepare_ban_change,
    require_self_deletion_lifecycle,
)
from studymate.application.operator.authority import (
    OperatorAccessDeniedError,
    OperatorPrincipal,
    require_operator,
)
from studymate.domain.lifecycle.states import (
    AccountLifecycle,
    LifecycleOperation,
    LifecycleReason,
    plan_ban_change,
    plan_deletion,
)
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore
from tests.unit.lifecycle.test_states import ACCOUNT, ACTOR, REASON, SESSION, WORKFLOW, evidence
from tests.unit.operator.store import Store
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER

KEY = IntentKey("lifecycle-intent-001")


def command(*, banned: bool = True) -> ChangeAccountBanCommand:
    return ChangeAccountBanCommand(CREDENTIAL, ACCOUNT, banned, LifecycleReason(REASON), KEY)


def deletion() -> DeleteOwnAccountCommand:
    return DeleteOwnAccountCommand(CREDENTIAL, WORKFLOW, KEY)


async def test_ban_uses_actual_shared_operator_guard_and_real_source_session() -> None:
    store = Store()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    principal = await require_operator(store, CREDENTIAL, HASHER)
    result = prepare_ban_change(principal, AccountLifecycle(ACCOUNT), command(), uuid4(), NOW)
    assert result.revision is not None
    assert result.revision.operator_access == principal.access
    assert result.revision.actor_session_id == store.actor.session.id
    assert result.revision.reason.value == REASON
    assert not result.after.account_allows_student_actions
    unban = prepare_ban_change(
        principal, replace(result.after, deleted_at=NOW), command(banned=False), uuid4(), NOW
    )
    assert unban.after.banned_at is None
    assert unban.after.deleted_at == NOW
    assert not unban.after.account_allows_student_actions
    assert not store.audit  # A planned lifecycle source is NOT an invented inspection receipt.


async def test_no_role_is_inferred_and_stale_operator_source_fails_closed() -> None:
    store = Store()
    with pytest.raises(OperatorAccessDeniedError):
        await require_operator(store, CREDENTIAL, HASHER)
    store.assign_explicit_operator()
    principal = await require_operator(store, CREDENTIAL, HASHER)
    stale = replace(principal, identity=replace(principal.identity, banned=True))
    with pytest.raises(OperatorAccessDeniedError):
        prepare_ban_change(stale, AccountLifecycle(ACCOUNT), command(), uuid4(), NOW)
    revoked = replace(principal, access=replace(principal.access, active=False))
    with pytest.raises(OperatorAccessDeniedError):
        prepare_ban_change(revoked, AccountLifecycle(ACCOUNT), command(), uuid4(), NOW)
    with pytest.raises(UnauthenticatedError):
        prepare_ban_change(
            principal,
            AccountLifecycle(ACCOUNT),
            command(),
            uuid4(),
            principal.identity.session.expires_at,
        )
    deleted_actor = replace(principal, identity=replace(principal.identity, deleted_at=NOW))
    with pytest.raises(UnauthenticatedError):
        prepare_ban_change(deleted_actor, AccountLifecycle(ACCOUNT), command(), uuid4(), NOW)
    wrong_actor = OperatorPrincipal(
        principal.identity, replace(principal.access, account_id=uuid4())
    )
    with pytest.raises(RuntimeError, match="another actual session account"):
        prepare_ban_change(wrong_actor, AccountLifecycle(ACCOUNT), command(), uuid4(), NOW)
    with pytest.raises(RuntimeError, match="another requested account"):
        prepare_ban_change(principal, AccountLifecycle(uuid4()), command(), uuid4(), NOW)


@pytest.mark.parametrize("banned", [True, False])
def test_self_deletion_lifecycle_slice_allows_limited_banned_account_management(
    banned: bool,
) -> None:
    store = IdentityStore()
    identity = replace(
        store.actor, membership=None, registration=None, activation_complete=False, banned=banned
    )
    state = AccountLifecycle(identity.session.account_id, NOW if banned else None)
    require_self_deletion_lifecycle(identity, state, NOW)
    check_submission_session_deadline(identity, NOW)
    with pytest.raises(UnauthenticatedError):
        require_self_deletion_lifecycle(identity, replace(state, deleted_at=NOW), NOW)
    with pytest.raises(UnauthenticatedError):
        require_self_deletion_lifecycle(replace(identity, deleted_at=NOW), state, NOW)
    with pytest.raises(UnauthenticatedError):
        require_self_deletion_lifecycle(identity, state, identity.session.expires_at)
    with pytest.raises(RuntimeError, match="actual session account"):
        require_self_deletion_lifecycle(identity, AccountLifecycle(uuid4()), NOW)
    with pytest.raises(UnauthenticatedError):
        check_submission_session_deadline(identity, identity.session.expires_at)


async def test_ban_intent_exact_hmac_replays_original_and_changed_payload_conflicts() -> None:
    submitted = command()
    before = AccountLifecycle(ACCOUNT)
    result = plan_ban_change(before, banned=True, evidence=evidence(), reason=submitted.reason)
    digest = await FINGERPRINTER.fingerprint(submitted.fingerprint_parts(ACTOR))
    retained = LifecycleIntent(ACTOR, submitted.operation, KEY, digest, result)
    assert resolve_ban_intent(None, submitted, ACTOR, digest) is None
    assert resolve_ban_intent(retained, submitted, ACTOR, digest) is result
    for changed in (
        replace(submitted, reason=LifecycleReason(REASON + " ")),
        replace(submitted, account_id=uuid4()),
    ):
        fingerprint = await FINGERPRINTER.fingerprint(changed.fingerprint_parts(ACTOR))
        with pytest.raises(IdempotencyConflictError):
            resolve_ban_intent(retained, changed, ACTOR, fingerprint)
    assert REASON not in repr(submitted)
    assert REASON not in repr(retained)
    assert CREDENTIAL.value not in repr(submitted)
    assert KEY.value not in repr(retained)
    assert digest.hex() not in repr(retained)
    assert result.before is before
    assert retained.result is result


async def test_noop_ban_and_unban_results_preserve_original_without_new_source() -> None:
    for banned in (True, False):
        submitted = command(banned=banned)
        before = AccountLifecycle(ACCOUNT, NOW if banned else None)
        result = plan_ban_change(
            before, banned=banned, evidence=evidence(), reason=submitted.reason
        )
        digest = await FINGERPRINTER.fingerprint(submitted.fingerprint_parts(ACTOR))
        retained = LifecycleIntent(ACTOR, submitted.operation, KEY, digest, result)
        assert not result.changed
        assert result.revision is None
        assert resolve_ban_intent(retained, submitted, ACTOR, digest) is result
        assert result.after is before


async def test_ban_intent_source_actor_operation_key_and_target_cannot_switch() -> None:
    submitted = command()
    result = plan_ban_change(
        AccountLifecycle(ACCOUNT), banned=True, evidence=evidence(), reason=submitted.reason
    )
    digest = await FINGERPRINTER.fingerprint(submitted.fingerprint_parts(ACTOR))
    retained = LifecycleIntent(ACTOR, submitted.operation, KEY, digest, result)
    with pytest.raises(RuntimeError, match="another actor, operation or key"):
        resolve_ban_intent(retained, submitted, uuid4(), digest)
    with pytest.raises(RuntimeError, match="another actor, operation or key"):
        resolve_ban_intent(retained, command(banned=False), ACTOR, digest)
    with pytest.raises(RuntimeError, match="another actor, operation or key"):
        resolve_ban_intent(
            retained,
            replace(submitted, intent_key=IntentKey("different-intent-key")),
            ACTOR,
            digest,
        )
    wrong_target = plan_ban_change(
        AccountLifecycle(uuid4()), banned=True, evidence=evidence(), reason=submitted.reason
    )
    corrupt = replace(retained, result=wrong_target)
    with pytest.raises(RuntimeError, match="exact retained target"):
        resolve_ban_intent(corrupt, submitted, ACTOR, digest)
    with pytest.raises(ValueError, match="operator/flag"):
        replace(retained, actor_id=uuid4())
    with pytest.raises(ValueError, match="operator/flag"):
        replace(retained, operation=LifecycleOperation.UNBAN)


async def test_deletion_replay_original_revoked_session_only_not_new_authority() -> None:
    identity = IdentityStore().actor
    submitted = deletion()
    state = AccountLifecycle(identity.session.account_id, NOW - timedelta(days=1))
    result = plan_deletion(
        state, change_id=uuid4(), at=NOW, actor_session_id=identity.session.id, workflow_id=WORKFLOW
    )
    digest = await FINGERPRINTER.fingerprint(
        submitted.fingerprint_parts(identity.session.account_id, identity.session.id)
    )
    retained = LifecycleIntent(
        identity.session.account_id, submitted.operation, KEY, digest, result
    )
    revoked = replace(identity, deleted_at=NOW, banned=True, session=identity.session.revoke(NOW))
    assert resolve_deletion_intent(retained, submitted, revoked, digest) is result
    assert resolve_deletion_intent(None, submitted, revoked, digest) is None
    with pytest.raises(UnauthenticatedError):
        require_self_deletion_lifecycle(revoked, result.after, NOW)
    with pytest.raises(UnauthenticatedError):
        check_submission_session_deadline(revoked, NOW)
    assert result.after.banned_at == state.banned_at
    assert result.revision.actor_session_id == identity.session.id
    assert result.revision.workflow_id == WORKFLOW
    assert result.revision.operation == LifecycleOperation.DELETE
    assert CREDENTIAL.value not in repr(submitted)
    assert KEY.value not in repr(submitted)


async def test_deletion_payload_and_actual_receipt_session_workflow_must_match() -> None:
    identity = IdentityStore().actor
    submitted = deletion()
    result = plan_deletion(
        AccountLifecycle(identity.session.account_id),
        change_id=uuid4(),
        at=NOW,
        actor_session_id=identity.session.id,
        workflow_id=WORKFLOW,
    )
    digest = await FINGERPRINTER.fingerprint(
        submitted.fingerprint_parts(identity.session.account_id, identity.session.id)
    )
    retained = LifecycleIntent(
        identity.session.account_id, submitted.operation, KEY, digest, result
    )
    changed = replace(submitted, workflow_id=uuid4())
    different = await FINGERPRINTER.fingerprint(
        changed.fingerprint_parts(identity.session.account_id, identity.session.id)
    )
    with pytest.raises(IdempotencyConflictError):
        resolve_deletion_intent(retained, changed, identity, different)
    with pytest.raises(RuntimeError, match="original session/workflow"):
        resolve_deletion_intent(retained, changed, identity, digest)
    other_session = replace(identity, session=replace(identity.session, id=uuid4()))
    with pytest.raises(RuntimeError, match="original session/workflow"):
        resolve_deletion_intent(retained, submitted, other_session, digest)
    other_account = replace(identity, session=replace(identity.session, account_id=uuid4()))
    with pytest.raises(RuntimeError, match="another actor"):
        resolve_deletion_intent(retained, submitted, other_account, digest)
    with pytest.raises(ValueError, match="self-owned"):
        replace(retained, actor_id=uuid4())
    with pytest.raises(ValueError, match="self-owned"):
        replace(retained, operation=LifecycleOperation.BAN)
    with pytest.raises(ValueError, match="actual payload HMAC"):
        replace(retained, fingerprint=b"short")
    with pytest.raises(ValueError, match="actual payload HMAC"):
        resolve_deletion_intent(None, submitted, identity, b"short")


def test_command_scope_fields_are_exact_and_never_identity_or_recovery_grants() -> None:
    submitted = command()
    assert submitted.fingerprint_parts(ACTOR) == (
        "lifecycle.v1",
        str(ACTOR),
        "ban",
        str(ACCOUNT),
        REASON,
    )
    assert command(banned=False).operation == LifecycleOperation.UNBAN
    assert deletion().fingerprint_parts(ACTOR, SESSION) == (
        "lifecycle.v1",
        str(ACTOR),
        "delete",
        str(SESSION),
        str(WORKFLOW),
    )
    assert deletion().fingerprint_parts(uuid4(), SESSION) != deletion().fingerprint_parts(
        ACTOR, SESSION
    )
    assert deletion().fingerprint_parts(ACTOR, uuid4()) != deletion().fingerprint_parts(
        ACTOR, SESSION
    )
    assert str(UUID(int=0)) not in submitted.fingerprint_parts(ACTOR)
