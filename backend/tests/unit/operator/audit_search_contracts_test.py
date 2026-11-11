"""Strict filters and opaque purpose/grant/query/time bound cursors."""

from dataclasses import replace
from datetime import timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from studymate.application.operator.audit_search_ports import (
    OperatorAuditFilters,
    OperatorAuditPosition,
)
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.domain.operator.audit import OperatorResourceKind
from studymate.infrastructure.operator.audit_search_cursors import FernetOperatorAuditCursorCodec
from studymate.presentation.operator.audit_search_models import OperatorAuditQuery
from tests.unit.identity_store import NOW

CODEC = FernetOperatorAuditCursorCodec.from_key(b"k" * 32)
SCOPE = OperatorCursorScope(UUID(int=100), 1)
DIGEST = b"d" * 32


@pytest.mark.parametrize("trace", ["", "a" * 31, "a" * 33, "A" * 32, "0" * 32, "private raw error"])
def test_trace_filter_has_no_raw_text_fallback(trace: str) -> None:
    with pytest.raises(ValueError, match="nonzero trace"):
        OperatorAuditFilters(trace_id=trace)
    with pytest.raises(ValidationError):
        OperatorAuditQuery.model_validate({"trace_id": trace})


def test_requested_id_is_typed_and_times_are_aware_nonempty_half_open() -> None:
    with pytest.raises(ValueError, match="exact requested resource kind"):
        OperatorAuditFilters(requested_id=uuid4())
    with pytest.raises(ValueError, match="include a timezone"):
        OperatorAuditFilters(occurred_from=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="nonempty half-open"):
        OperatorAuditFilters(occurred_from=NOW, occurred_before=NOW)
    first = OperatorAuditFilters(
        requested_kind=OperatorResourceKind.ACCOUNT,
        occurred_from=NOW,
        occurred_before=NOW + timedelta(seconds=1),
    )
    shifted = replace(first, occurred_from=NOW.astimezone(timezone(timedelta(hours=8))))
    assert first.fingerprint_parts() == shifted.fingerprint_parts()
    with pytest.raises(ValidationError):
        OperatorAuditQuery.model_validate({"result_id": str(uuid4())})
    with pytest.raises(ValidationError):
        OperatorAuditQuery.model_validate({"email": "private-sentinel"})


def test_cursor_is_opaque_and_bound_to_actor_grant_query_and_anchor() -> None:
    position = OperatorAuditPosition(NOW, NOW - timedelta(seconds=1), uuid4())
    token = CODEC.encode_audits(SCOPE, DIGEST, position)
    assert str(position.audit_id) not in token
    assert CODEC.decode_audits(SCOPE, DIGEST, token, NOW) == position
    for scope in (replace(SCOPE, account_id=uuid4()), replace(SCOPE, access_version=2)):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_audits(scope, DIGEST, token, NOW)
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_audits(SCOPE, b"e" * 32, token, NOW)
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_audits(SCOPE, DIGEST, token, NOW - timedelta(seconds=2))
    middle = len(token) // 2
    replacement = "A" if token[middle] != "A" else "B"
    tampered = token[:middle] + replacement + token[middle + 1 :]
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_audits(SCOPE, DIGEST, tampered, NOW)
    with pytest.raises(ValueError, match="time anchor"):
        OperatorAuditPosition(NOW, NOW + timedelta(seconds=1), uuid4())
