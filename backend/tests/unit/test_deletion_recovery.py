import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.lifecycle.recovery import (
    DeletionStatusCredential,
    DeletionStatusUnavailableError,
    DeletionWorkflow,
    PrepareOwnDeletion,
    ReadOwnDeletionStatus,
)
from studymate.domain.lifecycle.states import DeletionRevision
from studymate.infrastructure.lifecycle.status_proofs import HmacDeletionStatusProofs
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW, IdentityStore

PROOFS = HmacDeletionStatusProofs(b"p" * 32)
HASHER = Sha256SessionHasher()


class RecoveryStore(IdentityStore):
    def __init__(self) -> None:
        super().__init__()
        self.workflow: DeletionWorkflow | None = None
        self.status_digest: bytes | None = None
        self.deletion: DeletionRevision | None = None
        self.creations = 0
        self.fail_commit = False
        self.expire_on_create = False
        self.expire_on_read = False
        self.serial = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self, _digest: bytes) -> AsyncIterator["RecoveryStore"]:
        async with self.serial:
            before = self.workflow, self.status_digest, self.creations
            try:
                yield self
                if self.fail_commit:
                    raise StorageUnavailableError
            except BaseException:
                self.workflow, self.status_digest, self.creations = before
                raise

    async def revoke_session(self, session_id: UUID, at: datetime) -> None:
        assert session_id == self.actor.session.id
        self.actor = replace(self.actor, session=replace(self.actor.session, revoked_at=at))

    async def latest_workflow(self, account_id: UUID, session_id: UUID) -> DeletionWorkflow | None:
        assert (account_id, session_id) == (self.actor.session.account_id, self.actor.session.id)
        return self.workflow

    async def create_workflow(self, workflow: DeletionWorkflow, status_digest: bytes) -> None:
        self.workflow, self.status_digest = workflow, status_digest
        self.creations += 1
        if self.expire_on_create:
            self.clock = workflow.authorization.expires_at

    async def workflow_for_status(self, status_digest: bytes) -> DeletionWorkflow | None:
        return self.workflow if status_digest == self.status_digest else None

    async def committed_deletion(self, workflow_id: UUID) -> DeletionRevision | None:
        assert self.workflow is not None
        assert self.workflow.authorization.id == workflow_id
        if self.expire_on_read:
            self.clock = self.workflow.authorization.expires_at
        return self.deletion


def prepare(store: RecoveryStore) -> PrepareOwnDeletion:
    return PrepareOwnDeletion(store, HASHER, PROOFS)


def status(store: RecoveryStore) -> ReadOwnDeletionStatus:
    return ReadOwnDeletionStatus(store, PROOFS)


async def test_lost_preflight_and_simultaneous_tabs_keep_same_unresolved_binding_and_secret() -> (
    None
):
    store = RecoveryStore()
    first, second = await asyncio.gather(prepare(store)(CREDENTIAL), prepare(store)(CREDENTIAL))
    assert first == second
    assert store.creations == 1
    assert await prepare(store)(CREDENTIAL) == first
    assert first.status_credential.value not in repr(first)
    assert PROOFS.digest(first.status_credential) == store.status_digest


async def test_only_expired_workflow_advances_generation_and_retires_old_status_proof() -> None:
    store = RecoveryStore()
    first = await prepare(store)(CREDENTIAL)
    store.clock = first.authorization.expires_at
    second = await prepare(store)(CREDENTIAL)
    assert first.authorization.id != second.authorization.id
    assert first.status_credential != second.status_credential
    assert store.workflow is not None
    assert store.workflow.generation > 1
    with pytest.raises(DeletionStatusUnavailableError):
        await status(store)(first.status_credential)


async def test_workflow_expiry_is_capped_at_actual_session_expiry() -> None:
    store = RecoveryStore()
    store.actor = replace(
        store.actor, session=replace(store.actor.session, expires_at=NOW + timedelta(minutes=1))
    )
    result = await prepare(store)(CREDENTIAL)
    assert result.authorization.expires_at == store.actor.session.expires_at


async def test_banned_unverified_account_can_prepare_limited_self_management() -> None:
    store = RecoveryStore()
    store.actor = replace(store.actor, banned=True, membership=None, activation_complete=False)
    result = await prepare(store)(CREDENTIAL)
    assert result.authorization.account_id == store.actor.session.account_id


@pytest.mark.parametrize("denial", ["deleted", "revoked", "expired"])
async def test_unavailable_session_cannot_prepare_new_deletion_workflow(denial: str) -> None:
    store = RecoveryStore()
    if denial == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
    elif denial == "revoked":
        await store.revoke_session(store.actor.session.id, NOW)
    else:
        store.clock = store.actor.session.expires_at
    with pytest.raises(UnauthenticatedError):
        await prepare(store)(CREDENTIAL)
    assert store.workflow is None


@pytest.mark.parametrize("failure", ["commit", "expiry"])
async def test_failed_preflight_does_not_commit_a_new_workflow(failure: str) -> None:
    store = RecoveryStore()
    store.fail_commit = failure == "commit"
    store.expire_on_create = failure == "expiry"
    error = StorageUnavailableError if failure == "commit" else DeletionStatusUnavailableError
    with pytest.raises(error):
        await prepare(store)(CREDENTIAL)
    assert store.workflow is None
    assert store.status_digest is None


async def test_pending_and_committed_status_do_not_restore_the_deleted_session() -> None:
    store = RecoveryStore()
    prepared = await prepare(store)(CREDENTIAL)
    pending = await status(store)(prepared.status_credential)
    assert pending.deletion is None
    authorization = prepared.authorization
    store.deletion = DeletionRevision(
        uuid4(), authorization.account_id, 1, NOW, authorization.session_id, authorization.id
    )
    store.actor = replace(
        store.actor,
        deleted_at=NOW,
        session=replace(store.actor.session, revoked_at=NOW),
    )
    confirmed = await status(store)(prepared.status_credential)
    assert confirmed.deletion == store.deletion
    assert store.actor.session.revoked_at == NOW
    assert store.actor.deleted_at == NOW


@pytest.mark.parametrize("invalid", ["credential", "expired", "expires_during_read"])
async def test_status_proof_and_final_expiry_are_checked_without_account_disclosure(
    invalid: str,
) -> None:
    store = RecoveryStore()
    prepared = await prepare(store)(CREDENTIAL)
    credential = prepared.status_credential
    if invalid == "credential":
        credential = DeletionStatusCredential("z" * 43)
    elif invalid == "expired":
        store.clock = prepared.authorization.expires_at
    else:
        store.expire_on_read = True
    with pytest.raises(DeletionStatusUnavailableError):
        await status(store)(credential)


async def test_status_refuses_an_unrelated_committed_deletion_source() -> None:
    store = RecoveryStore()
    prepared = await prepare(store)(CREDENTIAL)
    store.deletion = DeletionRevision(uuid4(), uuid4(), 1, NOW, uuid4(), uuid4())
    with pytest.raises(RuntimeError, match="actual owned committed source"):
        await status(store)(prepared.status_credential)


@pytest.mark.parametrize("changed", ["workflow", "account", "session", "session_digest", "key"])
async def test_status_secret_is_bound_to_every_actual_owner_and_original_session_input(
    changed: str,
) -> None:
    store = RecoveryStore()
    prepared = await prepare(store)(CREDENTIAL)
    authorization = prepared.authorization
    digest = await HASHER.digest(CREDENTIAL)
    proofs = PROOFS
    if changed == "workflow":
        authorization = replace(authorization, id=uuid4())
    elif changed == "account":
        authorization = replace(authorization, account_id=uuid4())
    elif changed == "session":
        authorization = replace(authorization, session_id=uuid4())
    elif changed == "session_digest":
        digest = b"d" * 32
    else:
        proofs = HmacDeletionStatusProofs(b"k" * 32)
    assert proofs.issue(authorization, digest) != prepared.status_credential
    assert prepared.status_credential.value not in repr(prepared.status_credential)


@pytest.mark.parametrize("value", ["", "short", "x" * 44, "/" * 43])
def test_status_credential_is_bounded_and_opaque(value: str) -> None:
    with pytest.raises(ValueError, match="opaque narrow credential"):
        DeletionStatusCredential(value)


@pytest.mark.parametrize("invalid", ["account", "session", "session_expiry"])
async def test_preflight_refuses_a_workflow_outside_its_actual_session_scope(invalid: str) -> None:
    store = RecoveryStore()
    await prepare(store)(CREDENTIAL)
    assert store.workflow is not None
    authorization = store.workflow.authorization
    if invalid == "account":
        authorization = replace(authorization, account_id=uuid4())
    elif invalid == "session":
        authorization = replace(authorization, session_id=uuid4())
    else:
        authorization = replace(
            authorization, expires_at=store.actor.session.expires_at + timedelta(seconds=1)
        )
    store.workflow = replace(store.workflow, authorization=authorization)
    with pytest.raises(RuntimeError, match=r"session-owned source|outlives its original session"):
        await prepare(store)(CREDENTIAL)


async def test_session_expiry_during_preflight_rolls_back_preparation() -> None:
    store = RecoveryStore()
    store.actor = replace(
        store.actor, session=replace(store.actor.session, expires_at=NOW + timedelta(minutes=1))
    )
    store.expire_on_create = True
    with pytest.raises(UnauthenticatedError):
        await prepare(store)(CREDENTIAL)
    assert store.workflow is None


@pytest.mark.parametrize("generation", [0, -1, True])
async def test_workflow_generation_cannot_fabricate_legacy_or_boolean_sources(
    generation: int,
) -> None:
    store = RecoveryStore()
    prepared = await prepare(store)(CREDENTIAL)
    with pytest.raises(ValueError, match="actual session generation"):
        DeletionWorkflow(prepared.authorization, generation, NOW)


async def test_workflow_creation_cannot_follow_its_fixed_expiry() -> None:
    store = RecoveryStore()
    prepared = await prepare(store)(CREDENTIAL)
    with pytest.raises(ValueError, match="expiry must follow"):
        DeletionWorkflow(prepared.authorization, 1, prepared.authorization.expires_at)


def test_status_derivation_refuses_short_server_key() -> None:
    with pytest.raises(ValueError, match="requires its server key"):
        HmacDeletionStatusProofs(b"short")


async def test_status_derivation_refuses_a_missing_original_session_digest() -> None:
    store = RecoveryStore()
    prepared = await prepare(store)(CREDENTIAL)
    with pytest.raises(ValueError, match="original session digest"):
        PROOFS.issue(prepared.authorization, b"")
