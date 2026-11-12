from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.identity_links import ReadOperatorIdentityLinks, validate_links
from studymate.application.operator.identity_links_data import (
    IDENTITY_LINKS_PAGE_SIZE,
    OperatorIdentityLink,
)
from studymate.application.operator.identity_links_ports import (
    OperatorIdentityLinksPosition,
    OperatorIdentityLinksWindow,
)
from studymate.domain.operator.audit import OperatorAction, OperatorAuditOutcome
from studymate.infrastructure.operator.identity_links_cursors import (
    FernetOperatorIdentityLinksCursorCodec,
)
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.identity_links_store import LinksStore, account
from tests.unit.operator.store import TARGET
from tests.unit.operator.test_authorized_reads import HASHER

CODEC = FernetOperatorIdentityLinksCursorCodec.from_key(b"i" * 32)


def reader(store: LinksStore) -> ReadOperatorIdentityLinks:
    return ReadOperatorIdentityLinks(store, HASHER, CODEC)


async def test_retired_deleted_claims_return_only_after_same_transaction_audit() -> None:
    store = LinksStore()
    store.assign_explicit_operator()
    store.rows = (OperatorIdentityLink(account(UUID(int=20)), True, False),)
    result = await reader(store)(CREDENTIAL, TARGET)
    assert result is not None
    assert result.target.deleted_at == NOW
    assert result.target.google is not None
    assert result.target.google.retired_at == NOW
    assert result.links == store.rows
    assert result.next_cursor is None
    assert store.audit[0].action == OperatorAction.READ_ACCOUNT
    assert store.audit[0].results == (store.audit[0].requested,)
    assert "private-shared-subject" not in repr(result)
    assert "private-shared-subject" not in repr(store.audit)


@pytest.mark.parametrize("state", ["absent", "revoked", "banned", "deleted", "expired"])
async def test_private_source_requires_live_explicit_operator(state: str) -> None:
    store = LinksStore()
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
    with pytest.raises(
        UnauthenticatedError if state in {"deleted", "expired"} else OperatorAccessDeniedError
    ):
        await reader(store)(CREDENTIAL, TARGET)
    assert store.private_queries == 0
    assert not store.audit


@pytest.mark.parametrize("failure", ["audit", "expiry_query", "expiry_audit"])
async def test_no_private_return_when_audit_or_final_session_fails(failure: str) -> None:
    store = LinksStore()
    store.assign_explicit_operator()
    store.fail_audit = failure == "audit"
    store.expire_after_query = failure == "expiry_query"
    store.expire_after_audit = failure == "expiry_audit"
    with pytest.raises(StorageUnavailableError if failure == "audit" else UnauthenticatedError):
        await reader(store)(CREDENTIAL, TARGET)
    assert not store.audit


async def test_missing_and_unlinked_accounts_are_distinct_audited_outcomes() -> None:
    store = LinksStore()
    store.assign_explicit_operator()
    store.target = replace(account(), google=None)
    page = await reader(store)(CREDENTIAL, TARGET)
    assert page is not None
    assert page.links == ()
    store.target = None
    assert await reader(store)(CREDENTIAL, TARGET) is None
    assert store.audit[-1].outcome == OperatorAuditOutcome.NOT_FOUND
    assert store.audit[-1].results == ()


async def test_cursor_pagination_excludes_new_sources_and_keeps_tied_timestamp_order() -> None:
    store = LinksStore()
    store.assign_explicit_operator()
    store.rows = tuple(
        OperatorIdentityLink(account(UUID(int=value)), True, False) for value in range(100, 48, -1)
    )
    first = await reader(store)(CREDENTIAL, TARGET)
    assert first is not None
    assert first.next_cursor is not None
    assert len(first.links) == IDENTITY_LINKS_PAGE_SIZE
    store.rows = (
        OperatorIdentityLink(
            replace(account(UUID(int=200)), created_at=NOW + timedelta(seconds=1)), True, False
        ),
        *store.rows,
    )
    second = await reader(store)(CREDENTIAL, TARGET, first.next_cursor)
    assert second is not None
    assert second.next_cursor is None
    assert tuple(row.account.account_id.int for row in second.links) == (50, 49)
    assert second.as_of == first.as_of


@pytest.mark.parametrize("wrong", ["actor", "grant", "target", "claim", "tamper", "future"])
def test_cursor_cannot_change_authority_target_sources_or_time(wrong: str) -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    target = account()
    fingerprint = target.claim_fingerprint()
    position = OperatorIdentityLinksPosition(NOW, NOW - timedelta(days=1), uuid4())
    token = CODEC.encode_links(scope, TARGET, fingerprint, position)
    if wrong == "actor":
        scope = OperatorCursorScope(uuid4(), 1)
    elif wrong == "grant":
        scope = OperatorCursorScope(scope.account_id, 2)
    elif wrong == "target":
        target = replace(target, account_id=uuid4())
    elif wrong == "claim":
        fingerprint = b"z" * 32
    elif wrong == "tamper":
        token = token[:-2] + "xx"
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_links(
            scope,
            target.account_id,
            fingerprint,
            token,
            NOW - timedelta(seconds=1) if wrong == "future" else NOW,
        )


@pytest.mark.parametrize("fault", ["self", "duplicate", "ascending", "future", "forged", "excess"])
def test_source_invariants_reject_unrelated_or_unbounded_adapter_rows(fault: str) -> None:
    target = account()
    one = OperatorIdentityLink(account(UUID(int=20)), True, False)
    two = OperatorIdentityLink(account(UUID(int=21)), True, False)
    bad = {
        "self": (OperatorIdentityLink(target, True, False),),
        "duplicate": (one, one),
        "ascending": (one, two),
        "future": (
            OperatorIdentityLink(
                replace(one.account, created_at=NOW + timedelta(seconds=1)), True, False
            ),
        ),
        "forged": (replace(one, shared_institutional_email=True),),
        "excess": (one,) * (IDENTITY_LINKS_PAGE_SIZE + 2),
    }
    with pytest.raises(RuntimeError):
        validate_links(target, OperatorIdentityLinksWindow(NOW, None), bad[fault])
