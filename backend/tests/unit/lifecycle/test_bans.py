import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import SessionCredential, UnauthenticatedError
from studymate.application.lifecycle.ban_ports import LifecycleTargetUnavailableError
from studymate.application.lifecycle.bans import ChangeAccountBan
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.domain.lifecycle.states import AccountLifecycle, LifecycleOperation, LifecycleReason
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.lifecycle.ban_store import BanStore, BanUnit
from tests.unit.lifecycle.test_application import command
from tests.unit.lifecycle.test_states import ACCOUNT, REASON
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER


def change(store: BanStore) -> ChangeAccountBan:
    return ChangeAccountBan(BanUnit(store), HASHER, FINGERPRINTER)


async def test_real_change_and_unban_preserve_deletion_original_source_and_history() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, registration=None, activation_complete=False
    )
    store.targets[ACCOUNT] = AccountLifecycle(ACCOUNT, deleted_at=NOW)
    message = store.append_message()
    submitted = command()
    result = await change(store)(submitted)
    assert result.changed
    assert result.after.deleted_at == NOW
    assert result.revision is not None
    assert result.revision.operator_access == store.access
    assert result.revision.actor_session_id == store.actor.session.id
    assert result.revision.reason.value == REASON
    assert result.revision.operation == LifecycleOperation.BAN
    assert store.received_scope == (await HASHER.digest(CREDENTIAL), ACCOUNT)
    assert store.calls == ["prior", "target", "apply", "remember"]
    assert store.sources == (result.revision,)
    assert store.canonical == (result.revision.id,)
    assert store.messages == (message,)
    assert not store.audit
    unban = await change(store)(command(banned=False))
    assert unban.changed
    assert unban.after.banned_at is None
    assert unban.after.deleted_at == NOW
    assert not unban.after.account_allows_student_actions
    assert unban.after.source_version == result.after.source_version + 1
    assert store.sources[0] == result.revision
    assert store.messages == (message,)
    assert not store.audit


async def test_self_ban_allowed_then_next_operator_command_denied() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    account_id = store.actor.session.account_id
    store.targets[account_id] = AccountLifecycle(account_id)
    result = await change(store)(replace(command(), account_id=account_id))
    assert result.changed
    assert store.actor.banned
    assert len(store.sources) == 1
    assert len(store.intents) == 1
    with pytest.raises(OperatorAccessDeniedError):
        await change(store)(
            replace(command(), account_id=account_id, intent_key=IntentKey("next-self-command"))
        )
    assert len(store.sources) == 1


@pytest.mark.parametrize("banned", [True, False])
async def test_noop_records_owned_intent_but_no_source_or_canonical_action(banned: bool) -> None:
    store = BanStore()
    store.assign_explicit_operator()
    state = AccountLifecycle(ACCOUNT, NOW if banned else None)
    store.targets[ACCOUNT] = state
    result = await change(store)(command(banned=banned))
    assert not result.changed
    assert result.after is state
    assert store.targets[ACCOUNT] is state
    assert len(store.intents) == 1
    assert not store.sources
    assert not store.canonical
    assert store.calls == ["prior", "target", "remember"]
    assert not store.audit


async def test_replay_original_receipt_after_current_flag_changes_without_reapplying() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    submitted = command()
    original = await change(store)(submitted)
    unban = await change(store)(command(banned=False))
    before_intents = store.intents.copy()
    before_sources = store.sources
    before_events = store.canonical
    store.calls = []
    repeated = await change(store)(submitted)
    assert repeated is original
    assert store.targets[ACCOUNT] == unban.after
    assert store.targets[ACCOUNT].banned_at is None
    assert store.calls == ["prior"]
    assert store.intents == before_intents
    assert store.sources == before_sources
    assert store.canonical == before_events


async def test_changed_payload_conflicts_before_target_lookup_or_mutation() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    submitted = command()
    await change(store)(submitted)
    store.calls = []
    before = store.targets.copy(), store.sources, store.canonical, store.intents.copy()
    with pytest.raises(IdempotencyConflictError):
        await change(store)(replace(submitted, reason=LifecycleReason(REASON + " ")))
    assert store.calls == ["prior"]
    assert (store.targets, store.sources, store.canonical, store.intents) == before


@pytest.mark.parametrize(
    "fault",
    ["missing", "unknown_credential", "no_role", "revoked_role", "banned", "deleted", "expired"],
)
async def test_current_authority_before_intent_or_target_lookup(fault: str) -> None:
    store = BanStore()
    store.assign_explicit_operator()
    submitted = command()
    error: type[UnauthenticatedError] | type[OperatorAccessDeniedError] = OperatorAccessDeniedError
    if fault == "missing":
        store.missing_identity = True
        error = UnauthenticatedError
    elif fault == "unknown_credential":
        submitted = replace(submitted, credential=SessionCredential("z" * 43))
        error = UnauthenticatedError
    elif fault == "no_role":
        store.access = None
    elif fault == "revoked_role":
        assert store.access is not None
        store.access = replace(store.access, active=False)
    elif fault == "banned":
        store.actor = replace(store.actor, banned=True)
    elif fault == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
        error = UnauthenticatedError
    else:
        store.clock = store.actor.session.expires_at
        error = UnauthenticatedError
    with pytest.raises(error):
        await change(store)(submitted)
    assert not store.calls
    assert not store.intents
    assert not store.sources
    assert not store.audit


async def test_missing_target_typed_error_no_false_source_or_inspection() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    with pytest.raises(LifecycleTargetUnavailableError):
        await change(store)(replace(command(), account_id=uuid4()))
    assert store.calls == ["prior", "target"]
    assert not store.sources
    assert not store.canonical
    assert not store.intents
    assert not store.audit
    store.target_override = AccountLifecycle(uuid4())
    with pytest.raises(RuntimeError, match="another requested account"):
        await change(store)(command())
    assert not store.sources


@pytest.mark.parametrize("phase", ["apply", "remember", "commit", "expiry"])
async def test_all_effects_source_flags_intent_and_canonical_roll_back_together(phase: str) -> None:
    store = BanStore()
    store.assign_explicit_operator()
    store.fail_apply = phase == "apply"
    store.fail_remember = phase == "remember"
    store.fail_commit = phase == "commit"
    store.expire_after_apply = phase == "expiry"
    before = store.targets.copy()
    error = UnauthenticatedError if phase == "expiry" else StorageUnavailableError
    with pytest.raises(error):
        await change(store)(command())
    assert store.targets == before
    assert not store.sources
    assert not store.canonical
    assert not store.intents
    assert not store.audit


async def test_replay_final_session_expiry_withholds_committed_receipt() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    await change(store)(command())
    before = store.targets.copy(), store.sources, store.canonical, store.intents.copy()
    store.expire_after_prior = True
    with pytest.raises(UnauthenticatedError):
        await change(store)(command())
    assert (store.targets, store.sources, store.canonical, store.intents) == before


async def test_concurrent_fake_same_intent_only_one_source_and_cancellation_cleanup() -> None:
    store = BanStore()
    store.assign_explicit_operator()
    first, repeated = await asyncio.gather(change(store)(command()), change(store)(command()))
    assert repeated is first
    assert len(store.sources) == 1
    assert len(store.canonical) == 1
    assert len(store.intents) == 1
    store.pause_apply = True
    different = replace(command(banned=False), intent_key=IntentKey("cancelled-unban-intent"))
    before = store.targets.copy(), store.sources, store.canonical, store.intents.copy()
    task = asyncio.create_task(change(store)(different))
    try:
        await asyncio.wait_for(store.entered.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        store.release.set()
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert (store.targets, store.sources, store.canonical, store.intents) == before
    store.pause_apply = False
    retry = await asyncio.wait_for(change(store)(different), timeout=2)
    assert retry.changed
    assert retry.after.banned_at is None
    assert len(store.sources) == len((first, retry))
