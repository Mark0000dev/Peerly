from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.message_operations import (
    ReadOperatorMessageOperation,
    ReadOperatorMessageOperations,
)
from studymate.application.operator.message_operations_ports import OperatorMessageOperationPosition
from studymate.infrastructure.operator.message_operations_cursors import (
    FernetOperatorMessageOperationCursorCodec,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.message_operations_store import OperationsStore, operation
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import HASHER

CODEC = FernetOperatorMessageOperationCursorCodec.from_key(b"m" * 32)


def reader(store: OperationsStore) -> ReadOperatorMessageOperations:
    return ReadOperatorMessageOperations(store, HASHER, CODEC)


async def test_terminal_sources_preserve_confirmed_text_and_cancelled_absence() -> None:
    store = OperationsStore()
    store.assign_explicit_operator()
    page = await reader(store)(CREDENTIAL, TARGET)
    assert page is not None
    assert tuple(row.id.int for row in page.operations) == (3, 2, 1)
    assert page.operations[0].message is None
    assert page.operations[1].message is not None
    assert page.operations[1].message.text == "  private retained text  "
    assert "private retained text" not in repr(page)
    assert "private retained text" not in repr(store.audit)
    assert store.audit[-1].action.value == "read_account"


async def test_detail_missing_or_foreign_child_audits_existing_account_read() -> None:
    store = OperationsStore()
    store.assign_explicit_operator()
    read = ReadOperatorMessageOperation(store, HASHER)
    assert await read(CREDENTIAL, TARGET, UUID(int=2)) == store.operations[1]
    assert await read(CREDENTIAL, TARGET, uuid4()) is None
    assert store.audit[-1].outcome.value == "read"
    assert store.audit[-1].results[0].id == TARGET
    assert await read(CREDENTIAL, uuid4(), UUID(int=2)) is None
    assert store.audit[-1].outcome.value == "not_found"
    assert store.audit[-1].results == ()


async def test_page_bound_and_new_send_cutoff() -> None:
    store = OperationsStore()
    store.assign_explicit_operator()
    store.operations = tuple(operation(n) for n in range(52, 0, -1))
    first = await reader(store)(CREDENTIAL, TARGET)
    assert first is not None
    assert first.next_cursor is not None
    fresh = replace(
        operation(100),
        terminal_at=NOW + timedelta(seconds=1),
        cancelled_at=NOW + timedelta(seconds=1),
    )
    store.operations = (fresh, *store.operations)
    second = await reader(store)(CREDENTIAL, TARGET, first.next_cursor)
    assert second is not None
    assert tuple(row.id.int for row in second.operations) == (2, 1)
    assert second.next_cursor is None


@pytest.mark.parametrize("state", ["absent", "revoked", "banned", "deleted", "expired"])
async def test_no_operator_bypass_or_query_before_authority(state: str) -> None:
    store = OperationsStore()
    if state != "absent":
        store.assign_explicit_operator()
    if state == "revoked":
        assert store.access is not None
        store.access = replace(store.access, active=False)
    elif state == "banned":
        store.actor = replace(store.actor, banned=True)
    elif state == "deleted":
        store.actor = replace(store.actor, deleted_at=NOW)
    elif state == "expired":
        store.clock = store.actor.session.expires_at
    error = UnauthenticatedError if state in {"deleted", "expired"} else OperatorAccessDeniedError
    with pytest.raises(error):
        await reader(store)(CREDENTIAL, TARGET)
    assert store.private_queries == 0
    assert not store.audit


@pytest.mark.parametrize("failure", ["audit", "expiry_query", "expiry_audit"])
async def test_failure_does_not_return_private_operations(failure: str) -> None:
    store = OperationsStore()
    store.assign_explicit_operator()
    store.fail_audit = failure == "audit"
    store.expire_after_query = failure == "expiry_query"
    store.expire_after_audit = failure == "expiry_audit"
    with pytest.raises(StorageUnavailableError if failure == "audit" else UnauthenticatedError):
        await reader(store)(CREDENTIAL, TARGET)
    assert not store.audit


@pytest.mark.parametrize("scope_change", ["actor", "grant", "target", "tamper"])
def test_cursor_binds_actor_grant_target_and_cutoff(scope_change: str) -> None:
    scope, target = OperatorCursorScope(uuid4(), 1), uuid4()
    position = OperatorMessageOperationPosition(NOW, uuid4(), NOW)
    token = CODEC.encode_operations(scope, target, position)
    assert CODEC.decode_operations(scope, target, token) == position
    if scope_change == "actor":
        scope = OperatorCursorScope(uuid4(), 1)
    elif scope_change == "grant":
        scope = OperatorCursorScope(scope.account_id, 2)
    elif scope_change == "target":
        target = uuid4()
    else:
        token = str(uuid4())
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_operations(scope, target, token)


async def test_foreign_child_under_existing_account_has_container_read_audit() -> None:
    store = OperationsStore()
    store.assign_explicit_operator()
    other = uuid4()
    store.accounts.add(other)
    assert await ReadOperatorMessageOperation(store, HASHER)(CREDENTIAL, other, UUID(int=2)) is None
    assert store.audit[-1].outcome.value == "read"
    assert store.audit[-1].results[0].id == other


async def test_existing_empty_operations_are_not_a_missing_account() -> None:
    store = OperationsStore()
    store.assign_explicit_operator()
    store.operations = ()
    page = await reader(store)(CREDENTIAL, TARGET)
    assert page is not None
    assert page.operations == ()
    assert page.next_cursor is None
    assert store.audit[-1].outcome.value == "read"
    assert await reader(store)(CREDENTIAL, uuid4()) is None
    assert store.audit[-1].outcome.value == "not_found"


@pytest.mark.parametrize("fault", ["owner", "ascending", "duplicate", "excess"])
async def test_corrupt_source_order_or_scope_never_reaches_response(fault: str) -> None:
    store = OperationsStore()
    store.assign_explicit_operator()
    store.rows_override = {
        "owner": (operation(1, author_id=uuid4()),),
        "ascending": (operation(1), operation(2)),
        "duplicate": (operation(1), operation(1)),
        "excess": tuple(operation(1) for _ in range(52)),
    }[fault]
    with pytest.raises(RuntimeError, match="Message operations"):
        await reader(store)(CREDENTIAL, TARGET)
    assert not store.audit


def test_cancelled_operation_cannot_fabricate_confirmed_content() -> None:
    cancelled = operation(1)
    confirmed = operation(2, confirmed=True)
    with pytest.raises(ValueError, match="Cancelled operation"):
        replace(cancelled, message=confirmed.message)
    with pytest.raises(ValueError, match="Confirmed operation"):
        replace(confirmed, message=None)
