"""Manual attestation is privileged explicit source truth, never an OTP/activation path."""

from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.membership_verification import (
    ManuallyVerifyMembership,
    ManuallyVerifyMembershipCommand,
    ManualMembershipClaimConflictError,
    ManualMembershipPreconditionError,
    ManualMembershipUnavailableError,
    ReadManualMembershipContext,
)
from studymate.domain.identity import StudentEmail
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.membership_verification_store import (
    CHALLENGE_ID,
    EMAIL,
    GOOGLE_ID,
    ManualVerificationStore,
)
from tests.unit.operator.store import TARGET


def command() -> ManuallyVerifyMembershipCommand:
    return ManuallyVerifyMembershipCommand(
        CREDENTIAL, TARGET, GOOGLE_ID, CHALLENGE_ID, EMAIL, IntentKey("manual_intent_1")
    )


def verify(store: ManualVerificationStore) -> ManuallyVerifyMembership:
    return ManuallyVerifyMembership(
        store, Sha256SessionHasher(), HmacIntentFingerprinter(b"k" * 32)
    )


async def test_expired_submission_manual_source_retains_actual_operator_and_exact_replay() -> None:
    store = ManualVerificationStore()
    store.assign_explicit_operator()
    submitted = command()
    result = await verify(store)(submitted)
    assert result.operator == store.access
    assert result.actor_session_id == store.actor.session.id
    assert result.email == EMAIL
    assert ":c" in result.occurrence_key
    assert result.occurrence_key.endswith(store.actor.session.account_id.hex)
    assert EMAIL.value not in repr(result)
    assert await verify(store)(submitted) == result
    assert store.sources == [result]
    assert store.target is not None
    assert store.target.latest is not None
    assert store.target.latest.superseded_at == NOW
    assert store.target.latest.consumed_at is None
    assert not store.actor.activation_complete


@pytest.mark.parametrize(
    "denied",
    [
        "role",
        "revoked",
        "banned_operator",
        "deleted_target",
        "banned_target",
        "lineage",
        "no_google",
    ],
)
async def test_current_actor_and_target_guards_precede_any_manual_claim(denied: str) -> None:
    store = ManualVerificationStore()
    if denied != "role":
        store.assign_explicit_operator()
    if denied == "revoked":
        assert store.access is not None
        store.access = replace(store.access, active=False)
    elif denied == "banned_operator":
        store.actor = replace(store.actor, banned=True)
    elif denied in ("deleted_target", "banned_target", "lineage", "no_google"):
        assert store.target is not None
        store.target = replace(
            store.target,
            deleted=denied == "deleted_target",
            banned=denied == "banned_target",
            lineage_banned=denied == "lineage",
            google_identity_id=None if denied == "no_google" else GOOGLE_ID,
        )
    error = (
        OperatorAccessDeniedError
        if denied in ("role", "revoked", "banned_operator")
        else ManualMembershipPreconditionError
        if denied == "no_google"
        else ManualMembershipUnavailableError
    )
    with pytest.raises(error):
        await verify(store)(command())
    assert not store.sources
    assert not store.intents


@pytest.mark.parametrize(
    "changed", ["challenge", "email", "identity", "consumed", "superseded", "placeholder", "bound"]
)
async def test_manual_approval_cannot_rebind_stale_or_synthetic_sources(changed: str) -> None:
    store = ManualVerificationStore()
    store.assign_explicit_operator()
    assert store.target is not None
    latest = store.target.latest
    assert latest is not None
    if changed == "challenge":
        latest = replace(latest, id=uuid4())
    elif changed == "email":
        latest = replace(latest, email=StudentEmail("other@mail.apu.edu.my"))
    elif changed == "identity":
        store.target = replace(store.target, google_identity_id=uuid4())
    elif changed == "consumed":
        latest = replace(latest, consumed_at=NOW)
    elif changed == "superseded":
        latest = replace(latest, superseded_at=NOW)
    elif changed == "placeholder":
        latest = replace(latest, email=StudentEmail(f"peerly-stage-{TARGET.hex}@mail.apu.edu.my"))
    else:
        store.target = replace(store.target, has_binding=True)
    store.target = replace(store.target, latest=latest)
    error = (
        ManualMembershipPreconditionError
        if changed in ("challenge", "email", "identity")
        else ManualMembershipUnavailableError
    )
    with pytest.raises(error):
        await verify(store)(command())
    assert not store.sources


async def test_claim_conflict_and_final_session_or_commit_failure_rollback_every_effect() -> None:
    store = ManualVerificationStore()
    store.assign_explicit_operator()
    store.claim_conflict = True
    with pytest.raises(ManualMembershipClaimConflictError):
        await verify(store)(command())
    assert not store.sources
    store.claim_conflict = False
    store.expire_after_audit = True
    with pytest.raises(UnauthenticatedError):
        await verify(store)(command())
    assert not store.sources
    assert not store.intents
    store.clock = NOW
    store.expire_after_audit = False
    store.fail_commit = True
    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        await verify(store)(command())
    assert not store.sources
    assert not store.intents


async def test_changed_payload_conflicts_and_new_operation_cannot_replace_existing_binding() -> (
    None
):
    store = ManualVerificationStore()
    store.assign_explicit_operator()
    first = await verify(store)(command())
    with pytest.raises(IdempotencyConflictError):
        await verify(store)(
            replace(command(), expected_email=StudentEmail("other@mail.apu.edu.my"))
        )
    with pytest.raises(ManualMembershipUnavailableError):
        await verify(store)(replace(command(), intent_key=IntentKey("manual_intent_2")))
    assert store.sources == [first]


async def test_context_read_uses_actual_account_audit_even_for_ineligible_target() -> None:
    store = ManualVerificationStore()
    store.assign_explicit_operator()
    assert store.target is not None
    store.target = replace(store.target, deleted=True)
    result = await ReadManualMembershipContext(store, Sha256SessionHasher())(CREDENTIAL, TARGET)
    assert result == store.target
    assert store.audit[-1].requested is not None
    assert store.audit[-1].requested.id == TARGET
    assert store.audit[-1].results == (store.audit[-1].requested,)
    assert not store.sources
