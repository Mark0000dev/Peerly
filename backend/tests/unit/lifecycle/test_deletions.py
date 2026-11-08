import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import SessionCredential, UnauthenticatedError
from studymate.application.lifecycle.ban_ports import LifecycleTargetUnavailableError
from studymate.application.lifecycle.deletion_ports import DeletionWorkflowUnavailableError
from studymate.application.lifecycle.deletions import DeleteOwnAccount
from studymate.domain.lifecycle.states import (
    AccountLifecycle,
    DeletionTransition,
    LifecycleOperation,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.lifecycle.deletion_store import FOREIGN_ACCOUNT, DeletionStore, DeletionUnit
from tests.unit.lifecycle.test_application import deletion
from tests.unit.lifecycle.test_states import WORKFLOW
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER


def delete(store: DeletionStore) -> DeleteOwnAccount:
    return DeleteOwnAccount(DeletionUnit(store), HASHER, FINGERPRINTER)


@pytest.mark.parametrize("banned", [False, True])
async def test_live_account_management_deletes_all_owned_sessions_and_preserves_history(
    banned: bool,
) -> None:
    store = DeletionStore()
    account = store.actor.session.account_id
    original_session = store.actor.session.id
    store.actor = replace(
        store.actor, banned=banned, membership=None, registration=None, activation_complete=False
    )
    store.targets[account] = AccountLifecycle(account, NOW - timedelta(days=1) if banned else None)
    history = store.business_history.copy()
    google = store.google_identity_accounts.copy()
    institutional = store.institutional_address_accounts.copy()
    unbound = store.unbound_login_flows
    result = await delete(store)(deletion())
    assert result.after.account_id == account
    assert result.after.deleted_at == NOW
    assert result.after.banned_at == result.before.banned_at
    assert result.after.source_version == 1
    assert result.revision.actor_session_id == original_session
    assert result.revision.workflow_id == WORKFLOW
    assert result.revision.operation == LifecycleOperation.DELETE
    assert store.received_deletion_scope == (await HASHER.digest(CREDENTIAL), WORKFLOW)
    assert store.actor.deleted_at == NOW
    assert store.actor.session.revoked_at == NOW
    assert all(
        session.revoked_at == NOW
        for session in store.sessions.values()
        if session.account_id == account
    )
    assert all(
        session.revoked_at is None
        for session in store.sessions.values()
        if session.account_id != account
    )
    for owned in (
        store.unused_verification_accounts,
        store.delivery_accounts,
        store.attributable_login_accounts,
        store.pending_contact_accounts,
        store.pending_ai_accounts,
    ):
        assert account not in owned
        assert FOREIGN_ACCOUNT in owned
    assert store.business_history == history
    assert store.google_identity_accounts == google
    assert store.institutional_address_accounts == institutional
    assert store.unbound_login_flows == unbound
    assert store.deletion_sources == (result.revision,)
    assert store.canonical == (result.revision.id,)
    assert len(store.intents) == 1
    assert store.calls == ["workflow", "prior", "target", "delete_apply", "remember"]
    assert not store.audit


async def test_exact_original_revoked_session_receipt_replay_without_new_mutation() -> None:
    store = DeletionStore()
    submitted = deletion()
    original = await delete(store)(submitted)
    before = (
        store.targets.copy(),
        store.sessions.copy(),
        store.deletion_sources,
        store.canonical,
        store.intents.copy(),
    )
    store.calls = []
    replay = await delete(store)(submitted)
    assert replay is original
    assert store.calls == ["workflow", "prior"]
    assert (
        store.targets,
        store.sessions,
        store.deletion_sources,
        store.canonical,
        store.intents,
    ) == before
    with pytest.raises(UnauthenticatedError):
        await delete(store)(replace(submitted, intent_key=IntentKey("new-intent-after-deletion")))
    assert (
        store.targets,
        store.sessions,
        store.deletion_sources,
        store.canonical,
        store.intents,
    ) == before


async def test_revoked_credential_and_workflow_id_alone_cannot_initiate_deletion() -> None:
    store = DeletionStore()
    account = store.actor.session.account_id
    store.actor = replace(store.actor, session=store.actor.session.revoke(NOW))
    with pytest.raises(UnauthenticatedError):
        await delete(store)(deletion())
    assert store.calls == ["workflow", "prior"]
    assert store.targets[account].deleted_at is None
    assert not store.deletion_sources
    assert not store.intents
    store.calls = []
    with pytest.raises(UnauthenticatedError):
        await delete(store)(replace(deletion(), credential=SessionCredential("z" * 43)))
    assert not store.calls
    assert not store.intents


@pytest.mark.parametrize(
    "fault",
    [
        "missing_identity",
        "missing_proof",
        "unknown_workflow",
        "expired_workflow",
        "expired_session",
        "deleted_identity",
    ],
)
async def test_workflow_and_live_session_required_for_any_new_mutation(fault: str) -> None:
    store = DeletionStore()
    submitted = deletion()
    expected: type[UnauthenticatedError] | type[DeletionWorkflowUnavailableError] = (
        UnauthenticatedError
    )
    if fault == "missing_identity":
        store.missing_identity = True
    elif fault == "missing_proof":
        store.proof_available = False
        expected = DeletionWorkflowUnavailableError
    elif fault == "unknown_workflow":
        submitted = replace(submitted, workflow_id=uuid4())
        expected = DeletionWorkflowUnavailableError
    elif fault == "expired_workflow":
        store.authorization = replace(store.authorization, expires_at=NOW)
        expected = DeletionWorkflowUnavailableError
    elif fault == "expired_session":
        store.actor = replace(store.actor, session=replace(store.actor.session, expires_at=NOW))
    else:
        store.actor = replace(store.actor, deleted_at=NOW)
    with pytest.raises(expected):
        await delete(store)(submitted)
    assert not store.deletion_sources
    assert not store.intents
    assert not store.canonical
    assert "delete_apply" not in store.calls


@pytest.mark.parametrize("fault", ["workflow", "account", "session"])
async def test_authorization_returned_for_wrong_source_fails_closed(fault: str) -> None:
    store = DeletionStore()
    value = store.authorization
    store.authorization_override = (
        replace(value, id=uuid4())
        if fault == "workflow"
        else replace(value, account_id=uuid4())
        if fault == "account"
        else replace(value, session_id=uuid4())
    )
    with pytest.raises(RuntimeError, match="actual account/session/workflow"):
        await delete(store)(deletion())
    assert store.calls == ["workflow"]
    assert not store.intents
    assert not store.deletion_sources


async def test_new_mutation_requires_exact_locked_identity_and_actual_owned_target() -> None:
    switched = DeletionStore()
    switched.switch_second_identity = True
    with pytest.raises(RuntimeError, match="locked original session"):
        await delete(switched)(deletion())
    assert not switched.deletion_sources
    missing = DeletionStore()
    del missing.targets[missing.actor.session.account_id]
    with pytest.raises(LifecycleTargetUnavailableError):
        await delete(missing)(deletion())
    assert not missing.deletion_sources
    wrong = DeletionStore()
    wrong.target_override = AccountLifecycle(uuid4())
    with pytest.raises(RuntimeError, match="actual session account"):
        await delete(wrong)(deletion())
    assert not wrong.intents
    deleted = DeletionStore()
    deleted.targets[deleted.actor.session.account_id] = AccountLifecycle(
        deleted.actor.session.account_id, deleted_at=NOW
    )
    with pytest.raises(UnauthenticatedError):
        await delete(deleted)(deletion())
    assert not deleted.intents


async def test_changed_workflow_exact_intent_conflict_before_new_effects() -> None:
    store = DeletionStore()
    original = await delete(store)(deletion())
    store.authorization = replace(store.authorization, id=uuid4())
    changed = replace(deletion(), workflow_id=store.authorization.id)
    with pytest.raises(IdempotencyConflictError):
        await delete(store)(changed)
    assert store.deletion_sources == (original.revision,)
    assert len(store.intents) == 1


@pytest.mark.parametrize(
    "phase", ["apply", "remember", "commit", "session_deadline", "workflow_deadline"]
)
async def test_atomic_rollback_all_invalidations_source_canonical_intent(phase: str) -> None:
    store = DeletionStore()
    account = store.actor.session.account_id
    before_sessions = store.sessions.copy()
    store.fail_apply = phase == "apply"
    store.fail_remember = phase == "remember"
    store.fail_commit = phase == "commit"
    store.expire_after_apply = phase == "session_deadline"
    store.expire_workflow_after_apply = phase == "workflow_deadline"
    error = (
        UnauthenticatedError
        if phase == "session_deadline"
        else DeletionWorkflowUnavailableError
        if phase == "workflow_deadline"
        else StorageUnavailableError
    )
    with pytest.raises(error):
        await delete(store)(deletion())
    assert store.targets[account].deleted_at is None
    assert store.actor.deleted_at is None
    assert store.actor.session.revoked_at is None
    assert store.sessions == before_sessions
    assert not store.deletion_sources
    assert not store.canonical
    assert not store.intents
    for owned in (
        store.unused_verification_accounts,
        store.delivery_accounts,
        store.attributable_login_accounts,
        store.pending_contact_accounts,
        store.pending_ai_accounts,
    ):
        assert account in owned
        assert FOREIGN_ACCOUNT in owned


async def test_workflow_expiry_while_loading_target_prevents_any_apply() -> None:
    store = DeletionStore()
    store.expire_after_target = True
    with pytest.raises(DeletionWorkflowUnavailableError):
        await delete(store)(deletion())
    assert "delete_apply" not in store.calls
    assert not store.intents


async def test_committed_replay_bound_by_both_fixed_deadlines_and_late_clock() -> None:
    store = DeletionStore()
    original = await delete(store)(deletion())
    store.expire_workflow_after_prior = True
    with pytest.raises(DeletionWorkflowUnavailableError):
        await delete(store)(deletion())
    assert store.deletion_sources == (original.revision,)
    store.expire_workflow_after_prior = False
    store.clock = NOW
    store.authorization = replace(
        store.authorization, expires_at=store.actor.session.expires_at + timedelta(hours=1)
    )
    store.expire_after_prior = True
    with pytest.raises(UnauthenticatedError):
        await delete(store)(deletion())
    assert store.deletion_sources == (original.revision,)
    assert len(store.intents) == 1


async def test_concurrent_fake_replay_single_source_and_cancellation_rollback_cleanup() -> None:
    store = DeletionStore()
    first, repeated = await asyncio.gather(delete(store)(deletion()), delete(store)(deletion()))
    assert repeated is first
    assert len(store.deletion_sources) == 1
    assert len(store.canonical) == 1
    cancelled = DeletionStore()
    cancelled.pause_apply = True
    account = cancelled.actor.session.account_id
    task = asyncio.create_task(delete(cancelled)(deletion()))
    try:
        await asyncio.wait_for(cancelled.entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        cancelled.release.set()
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert cancelled.targets[account].deleted_at is None
    assert cancelled.actor.session.revoked_at is None
    assert not cancelled.deletion_sources
    assert not cancelled.intents
    assert account in cancelled.unused_verification_accounts
    cancelled.pause_apply = False
    retry = await asyncio.wait_for(delete(cancelled)(deletion()), timeout=2)
    assert retry.after.deleted_at == NOW


def test_authorization_requires_aware_fixed_expiry() -> None:
    store = DeletionStore()
    with pytest.raises(ValueError, match="timezone"):
        replace(store.authorization, expires_at=NOW.replace(tzinfo=None))
    assert store.authorization.is_valid(NOW)
    assert not store.authorization.is_valid(store.authorization.expires_at)


async def test_competing_new_intent_denial_cannot_rollback_a_committed_deletion() -> None:
    store = DeletionStore()
    first_command = deletion()
    other_command = replace(first_command, intent_key=IntentKey("different-competing-intent"))
    # Force BOTH callers to wait before any effects. A failed second transaction
    # must not restore a pre-first-commit snapshot over the committed deletion.
    async with store.serial:
        first_task = asyncio.create_task(delete(store)(first_command))
        other_task = asyncio.create_task(delete(store)(other_command))
        await asyncio.sleep(0)
    results = await asyncio.gather(first_task, other_task, return_exceptions=True)
    completed = tuple(result for result in results if isinstance(result, DeletionTransition))
    denied = tuple(result for result in results if isinstance(result, UnauthenticatedError))
    assert len(completed) == 1
    assert len(denied) == 1
    assert store.deletion_sources == (completed[0].revision,)
    assert store.canonical == (completed[0].revision.id,)
    assert len(store.intents) == 1
    assert store.actor.deleted_at == NOW
    assert store.actor.session.revoked_at == NOW
    assert all(
        session.revoked_at == NOW
        for session in store.sessions.values()
        if session.account_id == store.actor.session.account_id
    )
