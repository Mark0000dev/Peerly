from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from studymate.application.operator.filters import OperatorAccountFilters
from studymate.domain.identity import StudentEmail
from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.audit import (
    OPERATOR_ACCOUNT_PAGE_SIZE,
    OPERATOR_MESSAGE_PAGE_SIZE,
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from tests.unit.identity_store import NOW


def access() -> OperatorAccess:
    return OperatorAccess(uuid4(), 1, True, NOW)


def audit() -> OperatorAudit:
    return OperatorAudit(
        uuid4(),
        access(),
        OperatorAction.SEARCH_ACCOUNTS,
        None,
        (),
        NOW,
        OperatorAuditOutcome.SEARCH,
        b"x" * 32,
    )


@pytest.mark.parametrize("version", [0, -1, True])
def test_role_requires_an_actual_positive_revision(version: int) -> None:
    with pytest.raises(ValueError, match="revision"):
        OperatorAccess(uuid4(), version, True, NOW)


def test_future_assignment_and_revocation_do_not_mean_current_operator_access() -> None:
    original = access()
    assert original.is_active(NOW)
    assert not replace(original, changed_at=NOW + timedelta(seconds=1)).is_active(NOW)
    assert not replace(original, version=2, active=False).is_active(NOW)
    assert original.version == 1
    with pytest.raises(ValueError, match=r"timezone|aware"):
        replace(original, changed_at=datetime(2026, 11, 8))


def invalid_audit(violation: str) -> OperatorAudit:
    original = audit()
    account = OperatorResourceRef(OperatorResourceKind.ACCOUNT, uuid4())
    message = OperatorResourceRef(OperatorResourceKind.MESSAGE, uuid4())
    if violation == "inactive":
        result = replace(original, access=replace(original.access, active=False))
    elif violation == "duplicate":
        result = replace(original, results=(account, account))
    elif violation == "search_request":
        result = replace(original, requested=account)
    elif violation == "fingerprint":
        result = replace(original, query_fingerprint=b"x")
    elif violation == "wrong_kind":
        result = replace(original, results=(message,))
    elif violation == "oversized":
        result = replace(
            original,
            results=tuple(
                OperatorResourceRef(OperatorResourceKind.ACCOUNT, uuid4())
                for _ in range(OPERATOR_ACCOUNT_PAGE_SIZE + 1)
            ),
        )
    elif violation == "notfound_results":
        result = replace(
            original,
            action=OperatorAction.READ_ACCOUNT,
            requested=account,
            outcome=OperatorAuditOutcome.NOT_FOUND,
            query_fingerprint=None,
            results=(account,),
        )
    elif violation == "wrong_account":
        result = replace(
            original,
            action=OperatorAction.READ_ACCOUNT,
            requested=account,
            outcome=OperatorAuditOutcome.READ,
            query_fingerprint=None,
            results=(OperatorResourceRef(OperatorResourceKind.ACCOUNT, uuid4()),),
        )
    else:
        result = replace(
            original,
            action=OperatorAction.READ_CONVERSATION_MESSAGES,
            requested=OperatorResourceRef(OperatorResourceKind.CONVERSATION, uuid4()),
            outcome=OperatorAuditOutcome.READ,
            query_fingerprint=None,
            results=tuple(
                OperatorResourceRef(OperatorResourceKind.MESSAGE, uuid4())
                for _ in range(OPERATOR_MESSAGE_PAGE_SIZE + 1)
            ),
        )
    return result


@pytest.mark.parametrize(
    "violation",
    [
        "inactive",
        "duplicate",
        "search_request",
        "fingerprint",
        "wrong_kind",
        "oversized",
        "notfound_results",
        "wrong_account",
        "oversized_messages",
    ],
)
def test_audit_rejects_fabricated_or_unbounded_metadata(violation: str) -> None:
    with pytest.raises(
        ValueError, match=r"active|distinct|Search|bounded|Not-found|actual returned"
    ):
        invalid_audit(violation)


@pytest.mark.parametrize("name", ["", " ", "bad\x00name", "x" * 51])
def test_name_search_is_bounded_and_literal_text(name: str) -> None:
    with pytest.raises(ValueError, match=r"Text|maximum|exceeds"):
        OperatorAccountFilters(name=name)


def test_filters_use_only_actual_stored_identity_fields_and_hide_private_repr() -> None:
    value = OperatorAccountFilters(
        google_subject="private-source-subject",
        institutional_email=StudentEmail("synthetic@mail.apu.edu.my"),
        name=" Private   original name ",
        hidden=True,
        created_from=NOW - timedelta(days=1),
        created_before=NOW,
    )
    assert value.google_issuer == "https://accounts.google.com"
    assert value.name == "Private original name"
    assert "private-source-subject" not in repr(value)
    assert "synthetic@mail" not in repr(value)
    assert "Private original name" not in repr(value)
    assert "private-source-subject" in value.fingerprint_parts()
    assert not hasattr(value, "google_email")
    assert value.fingerprint_parts() != replace(value, hidden=False).fingerprint_parts()


def invalid_filters(violation: str) -> OperatorAccountFilters:
    if violation == "issuer":
        return OperatorAccountFilters(google_issuer="https://invented-provider.test")
    if violation == "subject":
        return OperatorAccountFilters(google_subject="x" * 256)
    if violation == "time":
        return OperatorAccountFilters(created_from=NOW, created_before=NOW)
    return OperatorAccountFilters(created_from=datetime(2026, 11, 8))


@pytest.mark.parametrize("violation", ["issuer", "subject", "time", "naive"])
def test_unsupported_identity_or_invalid_time_filter_is_not_silently_broadened(
    violation: str,
) -> None:
    with pytest.raises(ValueError, match=r"issuer|subject|interval|aware|timezone"):
        invalid_filters(violation)
