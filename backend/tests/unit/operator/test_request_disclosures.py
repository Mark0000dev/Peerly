from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.disclosure_ports import (
    OperatorDisclosureFilters,
    OperatorDisclosurePosition,
)
from studymate.application.operator.request_disclosures import ReadOperatorRequestDisclosures
from studymate.domain.operator.audit import OperatorAuditOutcome
from studymate.domain.operator.request_disclosures import OPERATOR_DISCLOSURE_PAGE_SIZE
from studymate.infrastructure.operator.cursors import encode_cursor
from studymate.infrastructure.operator.disclosure_cursors import (
    PURPOSE,
    FernetOperatorDisclosureCursorCodec,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.disclosure_store import DisclosureStore, disclosure, linked_ack
from tests.unit.operator.request_store import PEER, REQUEST
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import FINGERPRINTER, HASHER

CODEC = FernetOperatorDisclosureCursorCodec.from_key(b"d" * 32)


def reader(store: DisclosureStore) -> ReadOperatorRequestDisclosures:
    return ReadOperatorRequestDisclosures(store, HASHER, FINGERPRINTER, CODEC)


async def test_all_repeats_unacked_and_only_exact_page_linked_acks() -> None:
    store = DisclosureStore()
    store.assign_explicit_operator()
    store.actor = replace(
        store.actor, membership=None, activation_complete=False, registration=None
    )
    store.seed_many()
    page = await reader(store)(CREDENTIAL, TARGET, REQUEST, OperatorDisclosureFilters())
    assert page is not None
    assert page.next_cursor is not None
    assert len(page.disclosures) == OPERATOR_DISCLOSURE_PAGE_SIZE
    assert page.acknowledgements == store.acks[:1]
    assert page.anchor_created_at is not None
    assert page.anchor_created_at > NOW
    assert {row.stored_version for row in page.disclosures} == {1}
    assert page.request.current_version != page.disclosures[0].stored_version
    store.rows = (*store.rows, replace(disclosure(100), created_at=NOW + timedelta(days=1)))
    second = await reader(store)(
        CREDENTIAL, TARGET, REQUEST, OperatorDisclosureFilters(), page.next_cursor
    )
    assert second is not None
    assert len(second.disclosures) == len((1, 2, 3))
    assert not second.next_cursor
    assert {row.id for row in page.disclosures}.isdisjoint(row.id for row in second.disclosures)
    store.ack_override = (linked_ack(replace(store.rows[0], viewer_id=PEER)),)
    # An ACK naming a different viewer than the actual disclosed source fails closed.
    with pytest.raises(RuntimeError, match="exact page-linked"):
        await reader(store)(
            CREDENTIAL, TARGET, REQUEST, OperatorDisclosureFilters(), page.next_cursor
        )


async def test_participants_filters_legacy_origins_and_no_ack_inference() -> None:
    store = DisclosureStore()
    store.assign_explicit_operator()
    store.rows = (disclosure(), replace(disclosure(2), viewer_id=PEER, stored_version=2))
    actual = linked_ack(store.rows[0])
    store.acks = (actual,)
    for account in (TARGET, PEER):
        page = await reader(store)(CREDENTIAL, account, REQUEST, OperatorDisclosureFilters())
        assert page is not None
        assert page.request.includes(account)
        assert len(page.disclosures) == len(store.rows)
        assert page.acknowledgements == (actual,)
        assert page.disclosures[0].origin.trace_id == "legacy-source"
    for filters in (
        OperatorDisclosureFilters(viewer_id=TARGET),
        OperatorDisclosureFilters(stored_version=1),
        OperatorDisclosureFilters(disclosure_id=store.rows[0].id),
        OperatorDisclosureFilters(acknowledgement_id=actual.id),
        OperatorDisclosureFilters(
            created_from=store.rows[0].created_at, created_before=store.rows[1].created_at
        ),
    ):
        page = await reader(store)(CREDENTIAL, TARGET, REQUEST, filters)
        assert page is not None
        assert page.disclosures == store.rows[:1]
    empty = await reader(store)(
        CREDENTIAL, TARGET, REQUEST, OperatorDisclosureFilters(acknowledgement_id=uuid4())
    )
    assert empty is not None
    assert not empty.disclosures
    assert not empty.acknowledgements
    assert empty.anchor_disclosure_id is None
    store.reverse_participants()
    store.acks = ()
    assert await reader(store)(CREDENTIAL, TARGET, REQUEST, OperatorDisclosureFilters()) is not None


async def test_real_parent_missing_and_foreign_child_audits() -> None:
    store = DisclosureStore()
    store.assign_explicit_operator()
    assert await reader(store)(CREDENTIAL, TARGET, uuid4(), OperatorDisclosureFilters()) is None
    assert store.audit[-1].outcome == OperatorAuditOutcome.READ
    assert store.audit[-1].results[0].id == TARGET
    other = uuid4()
    store.accounts.add(other)
    assert await reader(store)(CREDENTIAL, other, REQUEST, OperatorDisclosureFilters()) is None
    assert store.audit[-1].requested is not None
    assert store.audit[-1].requested.id == other
    assert await reader(store)(CREDENTIAL, uuid4(), REQUEST, OperatorDisclosureFilters()) is None
    missing = store.audit[-1]
    assert missing.outcome == OperatorAuditOutcome.NOT_FOUND
    assert not missing.results


@pytest.mark.parametrize("failure", ["role", "audit", "expiry", "commit"])
async def test_live_guard_and_atomic_audit_withhold_data(failure: str) -> None:
    store = DisclosureStore()
    if failure != "role":
        store.assign_explicit_operator()
    store.fail_audit = failure == "audit"
    store.expire_after_audit = failure == "expiry"
    store.fail_commit = failure == "commit"
    error = (
        OperatorAccessDeniedError
        if failure == "role"
        else UnauthenticatedError
        if failure == "expiry"
        else StorageUnavailableError
    )
    with pytest.raises(error):
        await reader(store)(CREDENTIAL, TARGET, REQUEST, OperatorDisclosureFilters())
    assert not store.audit
    if failure == "role":
        assert store.private_queries == 0


@pytest.mark.parametrize(
    "fault",
    [
        "account",
        "request",
        "owner",
        "rows",
        "order",
        "filter",
        "participants",
        "ack",
        "duplicate_ack",
        "ack_filter",
    ],
)
async def test_untrusted_port_sources_fail_closed(fault: str) -> None:
    store = DisclosureStore()
    store.assign_explicit_operator()
    if fault == "account":
        store.account_override = uuid4()
    elif fault in ("request", "owner"):
        store.root_override = replace(
            store.request,
            id=uuid4() if fault == "request" else REQUEST,
            sender_id=uuid4(),
            recipient_id=uuid4(),
        )
    elif fault == "rows":
        store.rows_override = tuple(disclosure(i) for i in range(OPERATOR_DISCLOSURE_PAGE_SIZE + 2))
    elif fault == "order":
        store.rows_override = (disclosure(), disclosure())
    elif fault == "filter":
        store.rows_override = (disclosure(),)
    elif fault == "participants":
        store.rows_override = (replace(disclosure(), sender_id=PEER, recipient_id=TARGET),)
    elif fault == "ack":
        store.ack_override = (linked_ack(disclosure(10)),)
    elif fault == "duplicate_ack":
        ack = linked_ack(disclosure())
        store.ack_override = (ack, ack)
    else:
        store.rows_override = (disclosure(),)
        store.ack_override = ()
    filters = (
        OperatorDisclosureFilters(viewer_id=PEER)
        if fault == "filter"
        else OperatorDisclosureFilters(acknowledgement_id=uuid4())
        if fault == "ack_filter"
        else OperatorDisclosureFilters()
    )
    with pytest.raises(RuntimeError):
        await reader(store)(CREDENTIAL, TARGET, REQUEST, filters)
    assert not store.audit


async def test_cursor_scope_rejects_actor_grant_account_request_filter_and_tampering() -> None:
    scope = OperatorCursorScope(UUID(int=7), 1)
    digest = await FINGERPRINTER.fingerprint(OperatorDisclosureFilters().fingerprint_parts())
    position = OperatorDisclosurePosition(NOW, uuid4(), NOW - timedelta(seconds=1), uuid4())
    token = CODEC.encode(scope, TARGET, REQUEST, digest, position)
    assert CODEC.decode(scope, TARGET, REQUEST, digest, token) == position
    for actor, account, request, fingerprint, cursor in (
        (replace(scope, account_id=uuid4()), TARGET, REQUEST, digest, token),
        (replace(scope, access_version=2), TARGET, REQUEST, digest, token),
        (scope, PEER, REQUEST, digest, token),
        (scope, TARGET, uuid4(), digest, token),
        (scope, TARGET, REQUEST, b"x" * 32, token),
        (scope, TARGET, REQUEST, b"short", token),
        (scope, TARGET, REQUEST, digest, token[:-2] + "xx"),
        (scope, TARGET, REQUEST, digest, "broken"),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode(actor, account, request, fingerprint, cursor)
    for anchor, before in (
        ("not-time", str(uuid4())),
        (NOW.replace(tzinfo=None).isoformat(), str(uuid4())),
        (NOW.isoformat(), "bad-id"),
    ):
        malformed = encode_cursor(
            CODEC.cipher,
            (
                PURPOSE,
                str(scope.account_id),
                "1",
                str(TARGET),
                str(REQUEST),
                digest.hex(),
                anchor,
                str(uuid4()),
                NOW.isoformat(),
                before,
            ),
        )
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode(scope, TARGET, REQUEST, digest, malformed)
    with pytest.raises(ValueError, match="HMAC"):
        CODEC.encode(scope, TARGET, REQUEST, b"short", position)
    with pytest.raises(ValueError, match="32-byte"):
        FernetOperatorDisclosureCursorCodec.from_key(b"short")


@pytest.mark.parametrize("version", [0, -1, True, 1 << 31])
def test_domain_and_filter_reject_invalid_stored_versions(version: int) -> None:
    with pytest.raises(ValueError, match="stored version"):
        replace(disclosure(), stored_version=version)
    with pytest.raises(ValueError, match="bounded actual version"):
        OperatorDisclosureFilters(stored_version=version)


def test_aware_intervals_participants_positions_and_normalized_fingerprint() -> None:
    with pytest.raises(ValueError, match="participant"):
        replace(disclosure(), viewer_id=uuid4())
    with pytest.raises(ValueError, match="participant"):
        replace(disclosure(), sender_id=PEER)
    with pytest.raises(ValueError, match="timezone"):
        replace(disclosure(), created_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone"):
        OperatorDisclosureFilters(created_from=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="half-open"):
        OperatorDisclosureFilters(created_from=NOW, created_before=NOW)
    with pytest.raises(ValueError, match="anchor"):
        OperatorDisclosurePosition(NOW, UUID(int=1), NOW, UUID(int=2))
    left = OperatorDisclosureFilters(created_from=NOW)
    right = OperatorDisclosureFilters(created_from=NOW.astimezone(UTC))
    assert left.fingerprint_parts() == right.fingerprint_parts()
    assert datetime.fromisoformat(left.fingerprint_parts()[3]) == NOW
