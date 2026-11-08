import asyncio
from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.media_ports import OperatorProfileMediaAudit
from studymate.application.operator.media_read import (
    OPERATOR_MEDIA_READ_SECONDS,
    ReadOperatorProfileMedia,
)
from studymate.domain.media import MAX_PHOTO_BYTES, MediaObjectKind
from studymate.domain.operator.audit import OperatorAuditOutcome
from studymate.domain.operator.profile_media import (
    OperatorProfileMediaKind,
    OperatorProfileMediaRequest,
    OperatorProfileMediaSource,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.media_store import ATTEMPT, PRIVATE_BYTES, UPLOAD, MediaStore, Reader
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import HASHER

REQUEST = OperatorProfileMediaRequest(TARGET, UPLOAD, ATTEMPT, OperatorProfileMediaKind.ORIGINAL)


@pytest.mark.parametrize("kind", list(OperatorProfileMediaKind))
async def test_operator_read_has_two_short_transactions_and_audit_before_bytes(
    kind: OperatorProfileMediaKind,
) -> None:
    store = MediaStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    reader = Reader(store)
    request = replace(REQUEST, kind=kind)
    result = await ReadOperatorProfileMedia(store, HASHER, reader)(CREDENTIAL, request)
    assert result is not None
    assert result.data == PRIVATE_BYTES
    assert result.kind == kind
    assert PRIVATE_BYTES.decode() not in repr(result)
    assert store.transaction_count == len((1, 2))
    assert reader.references == [request.reference]
    assert request.reference.kind != MediaObjectKind.UPLOAD
    audit = store.media_audits[0]
    assert audit.outcome == OperatorAuditOutcome.READ
    assert audit.request == request
    assert audit.actual_source_upload_id == UPLOAD
    assert PRIVATE_BYTES.decode() not in repr(audit)
    assert not store.in_transaction


@pytest.mark.parametrize("missing_blob", [True, False])
async def test_missing_actual_source_and_missing_blob_have_truthful_audit(
    missing_blob: bool,
) -> None:
    store = MediaStore()
    store.assign_explicit_operator()
    reader = Reader(store, missing=missing_blob)
    if not missing_blob:
        store.source = None
    assert await ReadOperatorProfileMedia(store, HASHER, reader)(CREDENTIAL, REQUEST) is None
    assert bool(reader.references) == missing_blob
    audit = store.media_audits[0]
    assert audit.outcome == OperatorAuditOutcome.NOT_FOUND
    assert audit.actual_source_upload_id == (UPLOAD if missing_blob else None)


async def test_source_removed_during_storage_rechecks_and_audits_no_source_before_404() -> None:
    store = MediaStore()
    store.assign_explicit_operator()

    async def removed() -> None:
        store.source = None

    reader = Reader(store, callback=removed)
    assert await ReadOperatorProfileMedia(store, HASHER, reader)(CREDENTIAL, REQUEST) is None
    assert store.media_audits[0].actual_source_upload_id is None
    assert store.media_audits[0].outcome == OperatorAuditOutcome.NOT_FOUND


@pytest.mark.parametrize(
    "change", ["revoked", "new_grant", "banned", "deleted", "expired", "new_session", "new_actor"]
)
async def test_authority_changed_during_storage_never_releases_bytes(change: str) -> None:
    store = MediaStore()
    store.assign_explicit_operator()

    async def changed() -> None:
        assert store.access is not None
        if change == "revoked":
            store.access = replace(store.access, active=False)
        elif change == "new_grant":
            store.access = replace(store.access, version=2)
        elif change == "banned":
            store.actor = replace(store.actor, banned=True)
        elif change == "deleted":
            store.actor = replace(store.actor, deleted_at=NOW)
        elif change == "expired":
            store.clock = store.actor.session.expires_at
        elif change == "new_actor":
            account_id = uuid4()
            store.actor = replace(
                store.actor, session=replace(store.actor.session, account_id=account_id)
            )
            store.access = replace(store.access, account_id=account_id)
        else:
            store.actor = replace(store.actor, session=replace(store.actor.session, id=uuid4()))

    reader = Reader(store, callback=changed)
    error = (
        OperatorAccessDeniedError
        if change in ("revoked", "new_grant", "banned")
        else UnauthenticatedError
    )
    with pytest.raises(error):
        await ReadOperatorProfileMedia(store, HASHER, reader)(CREDENTIAL, REQUEST)
    assert not store.media_audits
    assert not store.in_transaction


async def test_initial_authority_precedes_source_or_storage() -> None:
    store = MediaStore()
    reader = Reader(store)
    with pytest.raises(OperatorAccessDeniedError):
        await ReadOperatorProfileMedia(store, HASHER, reader)(CREDENTIAL, REQUEST)
    assert store.private_queries == 0
    assert not reader.references


@pytest.mark.parametrize(
    "failure",
    ["audit", "final_expiry", "outage", "timeout", "empty", "oversized", "commit", "reader_bound"],
)
async def test_no_private_bytes_on_audit_or_bounded_storage_failure(failure: str) -> None:
    store = MediaStore()
    store.assign_explicit_operator()
    store.fail_audit = failure == "audit"
    store.expire_after_audit = failure == "final_expiry"
    store.fail_commit = failure == "commit"
    reader = Reader(
        store,
        unavailable=failure == "outage",
        timed_out=failure == "timeout",
        invalid_image=failure == "reader_bound",
    )
    if failure == "empty":
        reader.data = b""
    elif failure == "oversized":
        reader.data = bytes(MAX_PHOTO_BYTES + 1)
    error = UnauthenticatedError if failure == "final_expiry" else StorageUnavailableError
    with pytest.raises(error):
        await ReadOperatorProfileMedia(store, HASHER, reader)(CREDENTIAL, REQUEST)
    assert not store.media_audits


@pytest.mark.parametrize("phase", ["initial", "final"])
async def test_wrong_owner_or_attempt_source_is_not_a_read_grant(phase: str) -> None:
    store = MediaStore()
    store.assign_explicit_operator()
    foreign = OperatorProfileMediaSource(uuid4(), UPLOAD, ATTEMPT)

    async def changed() -> None:
        store.source = foreign

    reader = Reader(store, callback=changed if phase == "final" else None)
    if phase == "initial":
        store.source = foreign
    with pytest.raises(RuntimeError, match="actual requested owner/upload/attempt"):
        await ReadOperatorProfileMedia(store, HASHER, reader)(CREDENTIAL, REQUEST)
    assert not store.media_audits


async def test_storage_cancellation_drains_reader_without_audit() -> None:
    store = MediaStore()
    store.assign_explicit_operator()
    started = asyncio.Event()
    stopped = asyncio.Event()
    pause = asyncio.Event()

    async def blocked() -> None:
        started.set()
        try:
            await pause.wait()
        finally:
            stopped.set()

    reader = Reader(store, callback=blocked)
    task = asyncio.create_task(ReadOperatorProfileMedia(store, HASHER, reader)(CREDENTIAL, REQUEST))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
    assert not store.in_transaction
    assert not store.media_audits
    assert store.transaction_count == 1


def test_audit_cannot_invent_source_outcome_or_inactive_grant() -> None:
    store = MediaStore()
    store.assign_explicit_operator()
    assert store.access is not None
    valid = OperatorProfileMediaAudit(
        uuid4(), store.access, REQUEST, NOW, OperatorAuditOutcome.READ, UPLOAD
    )
    for source in (None, uuid4()):
        with pytest.raises(ValueError, match="known returned upload"):
            replace(valid, actual_source_upload_id=source)
    with pytest.raises(ValueError, match="read/not-found"):
        replace(valid, outcome=OperatorAuditOutcome.SEARCH)
    with pytest.raises(ValueError, match="actual active operator"):
        replace(valid, access=replace(store.access, active=False))
    with pytest.raises(ValueError, match="valid OperatorProfileMediaKind"):
        OperatorProfileMediaKind("upload")


async def test_exact_maximum_object_size_is_bounded_and_still_audited() -> None:
    store = MediaStore()
    store.assign_explicit_operator()
    reader = Reader(store, data=bytes(MAX_PHOTO_BYTES))
    result = await ReadOperatorProfileMedia(store, HASHER, reader)(CREDENTIAL, REQUEST)
    assert result is not None
    assert len(result.data) == MAX_PHOTO_BYTES
    assert store.media_audits[0].outcome == OperatorAuditOutcome.READ


async def test_actual_fixed_storage_deadline_cancels_and_drains_without_holding_sql() -> None:
    store = MediaStore()
    store.assign_explicit_operator()
    stopped = asyncio.Event()
    pause = asyncio.Event()

    async def blocked() -> None:
        assert not store.in_transaction
        try:
            await pause.wait()
        finally:
            stopped.set()

    reader = Reader(store, callback=blocked)
    operation = ReadOperatorProfileMedia(store, HASHER, reader)(CREDENTIAL, REQUEST)
    with pytest.raises(StorageUnavailableError):
        await asyncio.wait_for(operation, timeout=OPERATOR_MEDIA_READ_SECONDS + 5)
    assert stopped.is_set()
    assert store.transaction_count == 1
    assert not store.media_audits
