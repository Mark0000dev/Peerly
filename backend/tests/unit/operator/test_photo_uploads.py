from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.photo_ports import (
    OperatorPhotoFilters,
    OperatorPhotoHistoryHead,
    OperatorPhotoHistoryPosition,
    OperatorPhotoUploadRootPosition,
)
from studymate.application.operator.photo_uploads import (
    OperatorPhotoHistoryPage,
    ReadOperatorPhotoHistory,
    ReadOperatorPhotoUploads,
)
from studymate.domain.media import PhotoUploadState
from studymate.domain.operator.audit import OperatorAction, OperatorAuditOutcome
from studymate.domain.operator.photo_uploads import (
    OPERATOR_PHOTO_PAGE_SIZE,
    OperatorMediaOrigin,
    OperatorMediaOriginPhase,
    OperatorPhotoAttempt,
    OperatorPhotoAttemptOutcome,
    OperatorPublishedPhotoRef,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.infrastructure.operator.cursors import encode_cursor
from studymate.infrastructure.operator.photo_cursors import FernetOperatorPhotoCursorCodec
from studymate.presentation.operator.photo_models import photo_history_response
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.photo_store import DIGEST, FIRST_UPLOAD, PhotoStore, revision, root
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER

CODEC = FernetOperatorPhotoCursorCodec.from_key(b"p" * 32)


def roots(store: PhotoStore) -> ReadOperatorPhotoUploads:
    return ReadOperatorPhotoUploads(store, HASHER, FINGERPRINTER, CODEC)


def history(store: PhotoStore) -> ReadOperatorPhotoHistory:
    return ReadOperatorPhotoHistory(store, HASHER, CODEC)


def attempt(number: int = 1) -> OperatorPhotoAttempt:
    return OperatorPhotoAttempt(
        uuid4(),
        FIRST_UPLOAD,
        number,
        NOW,
        NOW + timedelta(minutes=1),
        None,
        None,
        OperatorPhotoAttemptOutcome.PROCESSING,
        None,
        None,
        None,
        None,
        None,
    )


async def test_raw_metadata_operator_only_no_student_policy_and_no_digest_repr() -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    page = await roots(store)(CREDENTIAL, TARGET, OperatorPhotoFilters())
    assert page is not None
    assert len(page.uploads) == len(store.roots)
    detail = await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)
    assert detail is not None
    assert tuple(row.version for row in detail.revisions) == (3, 2, 1)
    assert detail.revisions[0].updated_at < detail.revisions[-1].updated_at
    assert detail.upload.source_sha256 == DIGEST
    assert repr(DIGEST) not in repr(detail)
    assert detail.attempts_current == ()
    assert detail.origins == ()
    assert detail.latest_published_photo_ref is None
    assert store.audit[-1].action == OperatorAction.READ_ACCOUNT
    assert store.audit[-1].outcome == OperatorAuditOutcome.READ


async def test_container_audit_distinguishes_missing_account_from_missing_owned_child() -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    assert await history(store)(CREDENTIAL, TARGET, uuid4()) is None
    inspected = store.audit[-1]
    assert inspected.outcome == OperatorAuditOutcome.READ
    assert inspected.results[0].id == TARGET
    assert await history(store)(CREDENTIAL, uuid4(), FIRST_UPLOAD) is None
    missing = store.audit[-1]
    assert missing.outcome == OperatorAuditOutcome.NOT_FOUND
    assert not missing.results
    assert await roots(store)(CREDENTIAL, uuid4(), OperatorPhotoFilters()) is None
    store.roots = {}
    empty = await roots(store)(CREDENTIAL, TARGET, OperatorPhotoFilters())
    assert empty is not None
    assert empty.uploads == ()
    assert empty.anchor_created_at is None


async def test_root_pagination_actual_metadata_anchor_and_filters() -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    store.roots = {
        UUID(int=i): replace(root(UUID(int=i)), created_at=NOW + timedelta(minutes=i))
        for i in range(1, OPERATOR_PHOTO_PAGE_SIZE + 3)
    }
    filters = OperatorPhotoFilters(PhotoUploadState.UPLOADING, created_from=NOW)
    first = await roots(store)(CREDENTIAL, TARGET, filters)
    assert first is not None
    assert first.next_cursor is not None
    assert len(first.uploads) == OPERATOR_PHOTO_PAGE_SIZE
    assert first.anchor_created_at is not None
    assert first.anchor_created_at > first.observed_at
    newer = replace(root(uuid4()), created_at=NOW + timedelta(days=2))
    store.roots[newer.id] = newer
    second = await roots(store)(CREDENTIAL, TARGET, filters, first.next_cursor)
    assert second is not None
    assert len(second.uploads) == len((1, 2))
    assert second.next_cursor is None
    assert newer not in second.uploads
    with pytest.raises(InvalidOperatorCursorError):
        await roots(store)(CREDENTIAL, TARGET, OperatorPhotoFilters(), first.next_cursor)
    none = await roots(store)(CREDENTIAL, TARGET, OperatorPhotoFilters(PhotoUploadState.READY))
    assert none is not None
    assert not none.uploads
    upper = await roots(store)(CREDENTIAL, TARGET, OperatorPhotoFilters(created_before=NOW))
    assert upper is not None
    assert not upper.uploads


async def test_history_all_versions_independent_of_current_pointer_and_mutable_attempts() -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    store.revisions[FIRST_UPLOAD] = tuple(
        revision(i) for i in range(1, OPERATOR_PHOTO_PAGE_SIZE + 3)
    )
    stored = attempt()
    store.attempt_rows = (stored,)
    origin = OperatorMediaOrigin(
        FIRST_UPLOAD,
        OperatorMediaOriginPhase.CREATED,
        OperatorEventOrigin(uuid4(), None, None, None),
        NOW,
    )
    store.origin_rows = (origin,)
    store.publication = OperatorPublishedPhotoRef(TARGET, 7, FIRST_UPLOAD, 2, NOW)
    first = await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)
    assert first is not None
    assert first.next_cursor is not None
    assert first.anchor_version > first.upload.current_version
    assert first.attempts_current == (stored,)
    store.attempt_rows = (
        replace(stored, outcome=OperatorPhotoAttemptOutcome.INTERRUPTED, finished_at=NOW),
    )
    second = await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD, first.next_cursor)
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (2, 1)
    assert second.attempts_current != first.attempts_current
    assert first.origins == second.origins == (origin,)
    assert second.latest_published_photo_ref == store.publication
    store.revisions[FIRST_UPLOAD] = (revision(1),)
    with pytest.raises(InvalidOperatorCursorError):
        await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD, first.next_cursor)


@pytest.mark.parametrize("read_history", [True, False])
async def test_role_auth_and_audit_failure_return_no_content(read_history: bool) -> None:
    store = PhotoStore()
    operation = (
        history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)
        if read_history
        else roots(store)(CREDENTIAL, TARGET, OperatorPhotoFilters())
    )
    with pytest.raises(OperatorAccessDeniedError):
        await operation
    assert not store.audit
    store.assign_explicit_operator()
    store.actor = replace(store.actor, session=replace(store.actor.session, expires_at=NOW))
    operation = (
        history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)
        if read_history
        else roots(store)(CREDENTIAL, TARGET, OperatorPhotoFilters())
    )
    with pytest.raises(UnauthenticatedError):
        await operation


@pytest.mark.parametrize("bad", ["owner", "order", "filter", "bounds"])
async def test_root_source_integrity(bad: str) -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    value = root()
    if bad == "owner":
        value = root(account_id=uuid4())
    store.root_rows = (
        (value, value)
        if bad == "order"
        else (value,) * (OPERATOR_PHOTO_PAGE_SIZE + 2)
        if bad == "bounds"
        else (value,)
    )
    filters = (
        OperatorPhotoFilters(PhotoUploadState.READY) if bad == "filter" else OperatorPhotoFilters()
    )
    with pytest.raises(RuntimeError):
        await roots(store)(CREDENTIAL, TARGET, filters)
    assert not store.audit


@pytest.mark.parametrize("bad", ["owner", "order", "bounds", "future"])
async def test_revision_source_integrity(bad: str) -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    value = revision(1)
    if bad == "owner":
        value = replace(value, account_id=uuid4())
    if bad == "future":
        value = revision(999)
    store.revision_rows = (
        (value, value)
        if bad == "order"
        else (value,) * (OPERATOR_PHOTO_PAGE_SIZE + 2)
        if bad == "bounds"
        else (value,)
    )
    with pytest.raises(RuntimeError):
        await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)
    assert not store.audit


@pytest.mark.parametrize(
    "bad",
    [
        "attempt_owner",
        "attempt_duplicate",
        "attempt_order",
        "attempt_bounds",
        "origin_owner",
        "origin_duplicate",
        "origin_bounds",
        "publication",
    ],
)
async def test_auxiliary_source_integrity(bad: str) -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    value = attempt()
    if bad == "attempt_owner":
        store.attempt_rows = (replace(value, upload_id=uuid4()),)
    if bad == "attempt_duplicate":
        store.attempt_rows = (value, value)
    if bad == "attempt_order":
        store.attempt_rows = (attempt(2), value)
    if bad == "attempt_bounds":
        store.attempt_rows = tuple(attempt() for _ in range(4))
    origin = OperatorMediaOrigin(
        FIRST_UPLOAD,
        OperatorMediaOriginPhase.CREATED,
        OperatorEventOrigin(uuid4(), None, None, None),
        NOW,
    )
    if bad == "origin_owner":
        store.origin_rows = (replace(origin, upload_id=uuid4()),)
    if bad == "origin_duplicate":
        store.origin_rows = (origin, origin)
    if bad == "origin_bounds":
        store.origin_rows = (origin,) * 3
    if bad == "publication":
        store.publication = OperatorPublishedPhotoRef(uuid4(), 1, FIRST_UPLOAD, 1, NOW)
    with pytest.raises(RuntimeError):
        await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)
    assert not store.audit


async def test_bad_account_and_head_source_fail_closed() -> None:
    store = PhotoStore()
    store.assign_explicit_operator()
    store.account_override = uuid4()
    with pytest.raises(RuntimeError):
        await roots(store)(CREDENTIAL, TARGET, OperatorPhotoFilters())
    with pytest.raises(RuntimeError):
        await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)
    store.account_override = None
    store.head_override = OperatorPhotoHistoryHead(root(uuid4()), 3)
    with pytest.raises(RuntimeError):
        await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)


def test_cursor_scopes_are_purpose_actor_grant_account_upload_and_filter_bound() -> None:
    scope = OperatorCursorScope(TARGET, 1)
    digest = b"d" * 32
    pos = OperatorPhotoUploadRootPosition(NOW, FIRST_UPLOAD, NOW, FIRST_UPLOAD)
    token = CODEC.encode_roots(scope, TARGET, digest, pos)
    assert CODEC.decode_roots(scope, TARGET, digest, token) == pos
    for actual, account, fingerprint in (
        (OperatorCursorScope(uuid4(), 1), TARGET, digest),
        (OperatorCursorScope(TARGET, 2), TARGET, digest),
        (scope, uuid4(), digest),
        (scope, TARGET, b"x" * 32),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_roots(actual, account, fingerprint, token)
    point = OperatorPhotoHistoryPosition(3, 2)
    token = CODEC.encode_history(scope, TARGET, FIRST_UPLOAD, point)
    assert CODEC.decode_history(scope, TARGET, FIRST_UPLOAD, token) == point
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_history(scope, TARGET, uuid4(), token)
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_roots(scope, TARGET, digest, token)
    with pytest.raises(ValueError, match="configured32-byte"):
        FernetOperatorPhotoCursorCodec.from_key(b"short")
    with pytest.raises(ValueError, match="actual query HMAC"):
        CODEC.encode_roots(scope, TARGET, b"short", pos)
    with pytest.raises(ValueError, match="nonempty half-open"):
        OperatorPhotoFilters(created_from=NOW, created_before=NOW)
    with pytest.raises(ValueError, match="actual metadata anchor"):
        OperatorPhotoUploadRootPosition(NOW, FIRST_UPLOAD, NOW + timedelta(seconds=1), FIRST_UPLOAD)
    with pytest.raises(ValueError, match="actual version anchor"):
        OperatorPhotoHistoryPosition(1, 2)
    with pytest.raises(ValueError, match="actual bounded source version"):
        revision(0)


def test_raw_metadata_validation_and_nullable_attempt_publication_projection() -> None:

    value = root()
    with pytest.raises(ValueError, match="owned current revision"):
        replace(value, current_version=1)
    with pytest.raises(ValueError, match="bounded attempt number"):
        attempt(0)
    with pytest.raises(ValueError, match="actual positive source version"):
        OperatorPhotoHistoryHead(value, 0)
    display = replace(
        attempt(),
        outcome=OperatorPhotoAttemptOutcome.READY,
        display_width=32,
        display_height=24,
        display_size=42,
        display_sha256=DIGEST,
    )
    published = OperatorPublishedPhotoRef(TARGET, 7, FIRST_UPLOAD, 2, NOW)
    page = photo_history_response(
        OperatorPhotoHistoryPage(value, (revision(1),), None, 1, NOW, (display,), (), published)
    )
    assert page.attempts_current[0].display_sha256 == DIGEST.hex()
    assert page.latest_published_photo_ref is not None
    assert page.latest_published_photo_ref.photo_version == published.photo_version
    assert DIGEST.hex() not in repr(page)
    assert "storage_key" not in page.model_dump_json()


@pytest.mark.parametrize("family", ["roots", "history"])
async def test_authenticated_but_malformed_cursor_payload_is_not_an_authority(family: str) -> None:

    scope = OperatorCursorScope(TARGET, 1)
    digest = b"d" * 32
    values: tuple[str, ...]
    if family == "roots":
        values = (
            "operator-photo-roots-v1",
            str(TARGET),
            "1",
            str(TARGET),
            digest.hex(),
            "bad-date",
            str(FIRST_UPLOAD),
            NOW.isoformat(),
            str(FIRST_UPLOAD),
        )
        token = encode_cursor(CODEC.roots, values)
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_roots(scope, TARGET, digest, token)
    else:
        for anchor in ("bad-version", "03"):
            values = (
                "operator-photo-history-v1",
                str(TARGET),
                "1",
                str(TARGET),
                str(FIRST_UPLOAD),
                anchor,
                "2",
            )
            token = encode_cursor(CODEC.history, values)
            with pytest.raises(InvalidOperatorCursorError):
                CODEC.decode_history(scope, TARGET, FIRST_UPLOAD, token)
