from dataclasses import replace
from uuid import uuid4

import pytest

from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.infrastructure.operator.models import (
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.operator.timeline_values import audit_value
from studymate.presentation.operator.timeline_models import audit_response
from tests.unit.identity_store import NOW
from tests.unit.operator.media_store import ATTEMPT, UPLOAD, MediaStore
from tests.unit.operator.test_media_read import REQUEST
from tests.unit.operator.timeline_store import TimelineStore


def inspection() -> OperatorAudit:
    store = MediaStore()
    store.assign_explicit_operator()
    assert store.access is not None
    ref = OperatorResourceRef(OperatorResourceKind.PROFILE_MEDIA, UPLOAD)
    return OperatorAudit(
        uuid4(),
        store.access,
        OperatorAction.READ_MEDIA,
        ref,
        (ref,),
        NOW,
        OperatorAuditOutcome.READ,
        media_request=REQUEST,
        actual_source_upload_id=UPLOAD,
    )


@pytest.mark.parametrize(
    "fault",
    [
        "missing_metadata",
        "requested",
        "source",
        "read_without_source",
        "old_action_metadata",
        "old_action_source",
        "notfound_results",
        "missing_requested",
        "kind",
        "fingerprint",
    ],
)
def test_canonical_media_audit_requires_exact_shape_and_cannot_pollute_other_actions(
    fault: str,
) -> None:
    original = inspection()
    with pytest.raises(ValueError, match=r"media|Media|Inspection|Not-found"):
        invalid(original, fault)


def invalid(original: OperatorAudit, fault: str) -> None:
    if fault == "missing_metadata":
        replace(original, media_request=None)
    elif fault == "requested":
        replace(
            original, requested=OperatorResourceRef(OperatorResourceKind.PROFILE_MEDIA, uuid4())
        )
    elif fault == "source":
        replace(original, actual_source_upload_id=uuid4())
    elif fault == "read_without_source":
        replace(original, actual_source_upload_id=None)
    elif fault == "old_action_metadata":
        replace(original, action=OperatorAction.READ_ACCOUNT)
    elif fault == "old_action_source":
        replace(original, action=OperatorAction.READ_ACCOUNT, media_request=None)
    elif fault == "notfound_results":
        replace(original, outcome=OperatorAuditOutcome.NOT_FOUND)
    elif fault == "missing_requested":
        replace(original, requested=None)
    elif fault == "kind":
        replace(original, requested=OperatorResourceRef(OperatorResourceKind.ACCOUNT, UPLOAD))
    else:
        replace(original, query_fingerprint=b"x" * 32)


@pytest.mark.parametrize("known_source", [True, False])
def test_not_found_audit_preserves_known_source_without_inventing_blob_availability(
    known_source: bool,
) -> None:
    original = inspection()
    row = replace(
        original,
        outcome=OperatorAuditOutcome.NOT_FOUND,
        results=(),
        actual_source_upload_id=UPLOAD if known_source else None,
    )
    assert row.actual_source_upload_id == (UPLOAD if known_source else None)
    assert row.media_request == REQUEST


@pytest.mark.parametrize("fault", ["owner", "attempt", "kind", "unknown_kind"])
def test_audit_mapping_never_fabricates_incomplete_media_source(fault: str) -> None:
    original = inspection()
    grant = OperatorAccessRevisionRecord(
        account_id=original.access.account_id, version=1, active=True, changed_at=NOW
    )
    row = OperatorAuditRecord(
        id=original.id,
        operator_id=grant.account_id,
        operator_access_version=1,
        operator_access_active=True,
        action="read_media",
        resource_kind="profile_media",
        requested_id=UPLOAD,
        result_ids=[UPLOAD],
        outcome="read",
        occurred_at=NOW,
        requested_media_owner_id=REQUEST.account_id,
        requested_media_attempt_id=ATTEMPT,
        requested_media_kind="original",
        actual_source_upload_id=UPLOAD,
    )
    if fault == "owner":
        row.requested_media_owner_id = None
    elif fault == "attempt":
        row.requested_media_attempt_id = None
    elif fault == "kind":
        row.requested_media_kind = None
    else:
        row.requested_media_kind = "upload"
    error = ValueError if fault == "unknown_kind" else RuntimeError
    with pytest.raises(error, match=r"actual|OperatorProfileMediaKind"):
        audit_value(row, grant)


def test_legacy_audit_detail_has_explicit_null_media_metadata() -> None:
    store = TimelineStore()
    store.assign_explicit_operator()
    dto = audit_response(store.original_audit())
    assert dto.requested_media_owner_id is None
    assert dto.requested_media_attempt_id is None
    assert dto.requested_media_kind is None
    assert dto.actual_source_upload_id is None
