from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.chat_image_ports import (
    OperatorChatImageFilters,
    OperatorChatImageHistoryHead,
    OperatorChatImageHistoryPosition,
    OperatorChatImageUploadRootPosition,
)
from studymate.application.operator.chat_image_uploads import (
    ReadOperatorChatImageHistory,
    ReadOperatorChatImageUploads,
)
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.domain.chat_images import ChatImageState
from studymate.domain.messaging import MessageOutcome
from studymate.domain.operator.audit import OperatorAuditOutcome
from studymate.domain.operator.chat_image_uploads import (
    MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS,
    OPERATOR_CHAT_IMAGE_PAGE_SIZE,
    OperatorChatImageAttempt,
    OperatorChatImageAttemptOutcome,
    OperatorChatImageMatchingOperation,
)
from studymate.infrastructure.operator.chat_image_cursors import FernetOperatorChatImageCursorCodec
from studymate.infrastructure.operator.cursors import encode_cursor
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.chat_image_store import (
    DIGEST,
    FIRST_UPLOAD,
    ChatImageStore,
    revision,
    root,
)
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER

CODEC = FernetOperatorChatImageCursorCodec.from_key(b"i" * 32)


def roots(store: ChatImageStore) -> ReadOperatorChatImageUploads:
    return ReadOperatorChatImageUploads(store, HASHER, FINGERPRINTER, CODEC)


def history(store: ChatImageStore) -> ReadOperatorChatImageHistory:
    return ReadOperatorChatImageHistory(store, HASHER, CODEC)


def attempt(number: int = 1) -> OperatorChatImageAttempt:
    return OperatorChatImageAttempt(
        UUID(int=5000 + number),
        FIRST_UPLOAD,
        number,
        NOW,
        NOW + timedelta(seconds=10),
        NOW,
        None,
        OperatorChatImageAttemptOutcome.READY,
        None,
        10,
        10,
        100,
        DIGEST,
    )


def operation() -> OperatorChatImageMatchingOperation:
    source = root()
    return OperatorChatImageMatchingOperation(
        uuid4(),
        source.account_id,
        source.conversation_id,
        source.client_message_id,
        MessageOutcome.CONFIRMED,
        uuid4(),
        None,
    )


async def test_raw_revisions_independent_pointer_gaps_clock_and_current_attempts() -> None:
    store = ChatImageStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    store.revisions[FIRST_UPLOAD] = tuple(
        revision(index) for index in range(1, OPERATOR_CHAT_IMAGE_PAGE_SIZE + 4)
    )
    store.attempt_rows = tuple(
        attempt(index) for index in range(1, MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS + 1)
    )
    store.operation = operation()
    page = await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)
    assert page is not None
    assert page.next_cursor is not None
    assert page.anchor_version == max(row.version for row in store.revisions[FIRST_UPLOAD])
    assert page.upload.current_version != page.anchor_version
    assert len(page.revisions) == OPERATOR_CHAT_IMAGE_PAGE_SIZE
    assert page.revisions[0].updated_at < page.revisions[-1].updated_at
    assert page.attempts_current == store.attempt_rows
    assert page.matching_client_operation == store.operation
    assert DIGEST.hex() not in repr(page)
    second = await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD, page.next_cursor)
    assert second is not None
    assert tuple(row.version for row in second.revisions) == (3, 2, 1)
    assert second.next_cursor is None
    store.revisions[FIRST_UPLOAD] = (revision(1), revision(7), revision(99))
    store.attempt_rows = ()
    store.operation = None
    gaps = await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)
    assert gaps is not None
    assert tuple(row.version for row in gaps.revisions) == (99, 7, 1)
    assert not gaps.attempts_current
    assert gaps.matching_client_operation is None


async def test_metadata_filters_and_actual_future_keyset_anchor() -> None:
    store = ChatImageStore()
    store.assign_explicit_operator()
    store.roots = {}
    for index in range(1, OPERATOR_CHAT_IMAGE_PAGE_SIZE + 3):
        source = root(UUID(int=index))
        store.roots[source.id] = replace(source, created_at=NOW + timedelta(minutes=index))
    filters = OperatorChatImageFilters(
        conversation_id=root().conversation_id, state=ChatImageState.UPLOADING, created_from=NOW
    )
    first = await roots(store)(CREDENTIAL, TARGET, filters)
    assert first is not None
    assert first.next_cursor is not None
    assert first.anchor_created_at is not None
    assert first.anchor_created_at > NOW
    newer = root(uuid4())
    store.roots[newer.id] = replace(newer, created_at=NOW + timedelta(days=2))
    last = await roots(store)(CREDENTIAL, TARGET, filters, first.next_cursor)
    assert last is not None
    assert len(last.uploads) == len((1, 2))
    assert not last.next_cursor
    for query in (
        OperatorChatImageFilters(conversation_id=uuid4()),
        OperatorChatImageFilters(state=ChatImageState.REJECTED),
        OperatorChatImageFilters(created_before=NOW),
    ):
        empty = await roots(store)(CREDENTIAL, TARGET, query)
        assert empty is not None
        assert not empty.uploads
        assert empty.anchor_image_id is None


async def test_missing_parent_and_foreign_child_use_real_container_audit() -> None:
    store = ChatImageStore()
    store.assign_explicit_operator()
    assert await history(store)(CREDENTIAL, TARGET, uuid4()) is None
    assert store.audit[-1].outcome == OperatorAuditOutcome.READ
    assert store.audit[-1].results[0].id == TARGET
    stranger = uuid4()
    store.accounts.add(stranger)
    assert await history(store)(CREDENTIAL, stranger, FIRST_UPLOAD) is None
    assert await history(store)(CREDENTIAL, uuid4(), FIRST_UPLOAD) is None
    missing = store.audit[-1]
    assert missing.outcome == OperatorAuditOutcome.NOT_FOUND
    assert not missing.results
    assert await roots(store)(CREDENTIAL, uuid4(), OperatorChatImageFilters()) is None
    empty = await roots(store)(CREDENTIAL, stranger, OperatorChatImageFilters())
    assert empty is not None
    assert not empty.uploads


@pytest.mark.parametrize("read_history", [True, False])
@pytest.mark.parametrize("fault", ["role", "audit", "expiry"])
async def test_live_operator_and_atomic_audit_hold_private_metadata(
    read_history: bool, fault: str
) -> None:
    store = ChatImageStore()
    if fault != "role":
        store.assign_explicit_operator()
    store.fail_audit = fault == "audit"
    store.expire_after_audit = fault == "expiry"
    error = (
        OperatorAccessDeniedError
        if fault == "role"
        else UnauthenticatedError
        if fault == "expiry"
        else StorageUnavailableError
    )
    call = (
        history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)
        if read_history
        else roots(store)(CREDENTIAL, TARGET, OperatorChatImageFilters())
    )
    with pytest.raises(error):
        await call
    assert not store.audit


def bad_metadata(store: ChatImageStore, fault: str) -> None:
    if fault == "attempts":
        store.attempt_rows = (attempt(),) * (MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS + 1)
    elif fault == "attempt_owner":
        store.attempt_rows = (replace(attempt(), image_id=uuid4()),)
    elif fault == "attempt_duplicate":
        store.attempt_rows = (attempt(), attempt())
    elif fault == "attempt_order":
        store.attempt_rows = (attempt(2), attempt(1))
    else:
        value = operation()
        store.operation = (
            replace(value, author_id=uuid4())
            if fault == "operation_author"
            else replace(value, conversation_id=uuid4())
            if fault == "operation_conversation"
            else replace(value, client_message_id=uuid4())
        )


@pytest.mark.parametrize(
    "fault",
    [
        "account_root",
        "account_history",
        "head",
        "roots",
        "root_owner",
        "root_order",
        "root_filter",
        "revisions",
        "revision_owner",
        "revision_conversation",
        "revision_client",
        "revision_order",
        "attempts",
        "attempt_owner",
        "attempt_duplicate",
        "attempt_order",
        "operation_author",
        "operation_conversation",
        "operation_client",
    ],
)
async def test_source_scope_and_bounded_metadata_fail_closed(fault: str) -> None:
    store = ChatImageStore()
    store.assign_explicit_operator()
    if fault.startswith("account"):
        store.account_override = uuid4()
    elif fault == "head":
        store.head_override = OperatorChatImageHistoryHead(root(uuid4()), 3)
    elif fault == "roots":
        store.root_rows = tuple(
            root(UUID(int=index)) for index in range(1, OPERATOR_CHAT_IMAGE_PAGE_SIZE + 3)
        )
    elif fault == "root_owner":
        store.root_rows = (root(account_id=UUID(int=20)),)
    elif fault == "root_order":
        store.root_rows = (root(), root())
    elif fault == "root_filter":
        store.root_rows = (root(),)
    elif fault == "revisions":
        store.revision_rows = tuple(
            revision(index) for index in range(1, OPERATOR_CHAT_IMAGE_PAGE_SIZE + 3)
        )
    elif fault.startswith("revision_"):
        wrong = replace(revision(1))
        if fault == "revision_owner":
            wrong = replace(wrong, account_id=uuid4())
        elif fault == "revision_conversation":
            wrong = replace(wrong, conversation_id=uuid4())
        elif fault == "revision_client":
            wrong = replace(wrong, client_message_id=uuid4())
        store.revision_rows = (wrong, wrong) if fault == "revision_order" else (wrong,)
    else:
        bad_metadata(store, fault)
    filters = (
        OperatorChatImageFilters(state=ChatImageState.READY)
        if fault == "root_filter"
        else OperatorChatImageFilters()
    )
    call = (
        roots(store)(CREDENTIAL, TARGET, filters)
        if fault == "account_root" or fault.startswith("root")
        else history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD)
    )
    with pytest.raises(RuntimeError):
        await call
    assert not store.audit


async def test_cursor_scope_purposes_malformed_and_impossible_history_anchor() -> None:
    scope = OperatorCursorScope(UUID(int=1), 1)
    digest = await FINGERPRINTER.fingerprint(OperatorChatImageFilters().fingerprint_parts())
    position = OperatorChatImageUploadRootPosition(NOW, UUID(int=2), NOW, UUID(int=1))
    token = CODEC.encode_roots(scope, TARGET, digest, position)
    assert CODEC.decode_roots(scope, TARGET, digest, token) == position
    hp = OperatorChatImageHistoryPosition(3, 2)
    ht = CODEC.encode_history(scope, TARGET, FIRST_UPLOAD, hp)
    assert CODEC.decode_history(scope, TARGET, FIRST_UPLOAD, ht) == hp
    for actor, account, fingerprint, cursor in (
        (replace(scope, account_id=uuid4()), TARGET, digest, token),
        (replace(scope, access_version=2), TARGET, digest, token),
        (scope, uuid4(), digest, token),
        (scope, TARGET, b"x" * 32, token),
        (scope, TARGET, b"short", token),
        (scope, TARGET, digest, ht),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_roots(actor, account, fingerprint, cursor)
    for actor, account, image, cursor in (
        (replace(scope, access_version=2), TARGET, FIRST_UPLOAD, ht),
        (scope, uuid4(), FIRST_UPLOAD, ht),
        (scope, TARGET, uuid4(), ht),
        (scope, TARGET, FIRST_UPLOAD, token),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_history(actor, account, image, cursor)
    malformed = encode_cursor(
        CODEC.roots,
        (
            "operator-chat-image-roots-v1",
            str(scope.account_id),
            "1",
            str(TARGET),
            digest.hex(),
            "bad-time",
            str(uuid4()),
            NOW.isoformat(),
            str(uuid4()),
        ),
    )
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_roots(scope, TARGET, digest, malformed)
    for anchor, before in (("bad", "2"), ("3", "02"), ("3", "4")):
        malformed = encode_cursor(
            CODEC.history,
            (
                "operator-chat-image-history-v1",
                str(scope.account_id),
                "1",
                str(TARGET),
                str(FIRST_UPLOAD),
                anchor,
                before,
            ),
        )
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_history(scope, TARGET, FIRST_UPLOAD, malformed)
    with pytest.raises(ValueError, match="HMAC"):
        CODEC.encode_roots(scope, TARGET, b"short", position)
    with pytest.raises(ValueError, match="32-byte"):
        FernetOperatorChatImageCursorCodec.from_key(b"short")
    store = ChatImageStore()
    store.assign_explicit_operator()
    assert store.access is not None
    current = OperatorCursorScope(store.access.account_id, store.access.version)
    impossible = CODEC.encode_history(
        current, TARGET, FIRST_UPLOAD, OperatorChatImageHistoryPosition(99, 98)
    )
    with pytest.raises(InvalidOperatorCursorError):
        await history(store)(CREDENTIAL, TARGET, FIRST_UPLOAD, impossible)


@pytest.mark.parametrize("version", [0, True, 1 << 31])
def test_versions_and_attempt_bounds(version: int) -> None:
    with pytest.raises(ValueError, match="bounded source version"):
        replace(revision(1), version=version)
    with pytest.raises(ValueError, match="source version"):
        OperatorChatImageHistoryHead(root(), version)
    with pytest.raises(ValueError, match="version anchor"):
        OperatorChatImageHistoryPosition(version, version)
    with pytest.raises(ValueError, match="attempt number"):
        attempt(version)


def test_aware_metadata_and_actual_root_scope_are_preserved() -> None:
    with pytest.raises(ValueError, match="timezone"):
        OperatorChatImageFilters(created_from=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="half-open"):
        OperatorChatImageFilters(created_from=NOW, created_before=NOW)
    with pytest.raises(ValueError, match="metadata anchor"):
        OperatorChatImageUploadRootPosition(NOW, UUID(int=1), NOW, UUID(int=2))
    with pytest.raises(ValueError, match="owned current revision"):
        replace(root(), current_revision=revision(1))
    with pytest.raises(ValueError, match="timezone"):
        replace(operation(), cancelled_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone"):
        replace(attempt(), lease_until=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone"):
        replace(revision(1), updated_at=NOW.replace(tzinfo=None))
