import json
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.report_ports import (
    OperatorReportFilters,
    OperatorReportPosition,
)
from studymate.domain.operator.profile_reports import (
    OperatorProfileReportDetail,
    OperatorProfileReportSummary,
    OperatorReportSubmission,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.reports import ProfileAccessContext, ProfileVersionRefs, ReportCategory
from studymate.infrastructure.operator.report_cursors import FernetOperatorReportCursorCodec
from studymate.infrastructure.operator.report_values import report_detail_value
from studymate.infrastructure.operator.timeline_cursors import FernetOperatorEventCursorCodec
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportRecord,
)
from tests.unit.identity_store import NOW

CODEC = FernetOperatorReportCursorCodec.from_key(b"r" * 32)


def detail() -> OperatorProfileReportDetail:
    reporter, target, report_id, context_id = uuid4(), uuid4(), uuid4(), uuid4()
    context = ProfileAccessContext(
        context_id, reporter, ProfileVersionRefs(target, 1, 1, uuid4(), 2, 1), NOW
    )
    summary = OperatorProfileReportSummary(
        report_id, reporter, target, context_id, ReportCategory.OTHER, NOW - timedelta(days=1), True
    )
    return OperatorProfileReportDetail(
        summary,
        context,
        OperatorEventOrigin(uuid4()),
        "  Exact retained private note\nwith spaces  ",
        OperatorReportSubmission(
            uuid4(), report_id, reporter, NOW - timedelta(hours=1), OperatorEventOrigin(uuid4())
        ),
    )


def test_retained_source_does_not_reapply_submission_policy_or_conflate_origins() -> None:
    actual = detail()
    assert actual.report.submitted_at < actual.context.issued_at
    assert actual.comment == "  Exact retained private note\nwith spaces  "
    assert "Exact retained private" not in repr(actual)
    assert actual.submission is not None
    assert actual.context_origin.http_request_id != actual.submission.origin.http_request_id
    assert replace(actual, submission=None).submission is None


@pytest.mark.parametrize(
    "fault",
    [
        "self",
        "context",
        "context_owner",
        "context_target",
        "comment_flag",
        "comment_size",
        "other",
        "submission_id",
        "submission_owner",
    ],
)
def test_source_projections_require_exact_retained_ids_and_bounded_private_value(
    fault: str,
) -> None:
    actual = detail()
    with pytest.raises(ValueError, match=r"report|source|snapshot|explanation|comment"):
        invalid_source(actual, fault)


def invalid_source(actual: OperatorProfileReportDetail, fault: str) -> None:
    report = actual.report
    if fault == "self":
        replace(report, target_id=report.reporter_id)
    elif fault == "context":
        replace(actual, context=replace(actual.context, id=uuid4()))
    elif fault == "context_owner":
        replace(actual, context=replace(actual.context, viewer_id=uuid4()))
    elif fault == "context_target":
        replace(
            actual,
            context=replace(
                actual.context, snapshot=replace(actual.context.snapshot, account_id=uuid4())
            ),
        )
    elif fault == "comment_flag":
        replace(actual, report=replace(report, has_comment=False))
    elif fault == "comment_size":
        replace(actual, comment="x" * 1001)
    elif fault == "other":
        replace(actual, report=replace(report, has_comment=False), comment=None)
    elif fault == "submission_id":
        assert actual.submission is not None
        replace(actual, submission=replace(actual.submission, report_id=uuid4()))
    else:
        assert actual.submission is not None
        replace(actual, submission=replace(actual.submission, reporter_id=uuid4()))


def rows() -> tuple[ProfileReportRecord, ProfileAccessRecord, ProductEventRecord]:
    actual = detail()
    snapshot = actual.context.snapshot
    report = ProfileReportRecord(
        kind="profile",
        id=actual.report.id,
        reporter_id=actual.report.reporter_id,
        context_id=actual.context.id,
        category=actual.report.category.value,
        comment=actual.comment,
        submitted_at=actual.report.submitted_at,
    )
    context = ProfileAccessRecord(
        id=actual.context.id,
        viewer_id=actual.context.viewer_id,
        target_id=snapshot.account_id,
        profile_version=snapshot.profile_version,
        photo_version=snapshot.photo_version,
        goal_id=snapshot.goal_id,
        goal_version=snapshot.goal_version,
        help_version=snapshot.help_version,
        issued_at=actual.context.issued_at,
        request_id=actual.context_origin.http_request_id,
    )
    assert actual.submission is not None
    event = ProductEventRecord(
        id=actual.submission.event_id,
        account_id=actual.report.reporter_id,
        kind="report.created",
        report_id=actual.report.id,
        occurrence_key=f"report:{actual.report.id}",
        schema_version=1,
        occurred_at=actual.submission.occurred_at,
        request_id=actual.submission.origin.http_request_id,
    )
    return report, context, event


def test_report_mapping_preserves_exact_text_versions_and_separate_origins() -> None:
    report, context, event = rows()
    actual = report_detail_value(report, context, event)
    assert isinstance(actual, OperatorProfileReportDetail)
    assert actual.comment == report.comment
    assert actual.context.snapshot.profile_version == context.profile_version
    assert actual.context.snapshot.goal_version == context.goal_version
    assert actual.submission is not None
    assert actual.submission.event_id == event.id
    assert actual.submission.origin.http_request_id == event.request_id
    assert actual.context_origin.http_request_id == context.request_id
    assert report_detail_value(report, context, None).submission is None


@pytest.mark.parametrize("fault", ["kind", "report", "reporter", "occurrence"])
def test_unrelated_canonical_event_is_not_fabricated_as_report_submission(fault: str) -> None:
    report, context, event = rows()
    if fault == "kind":
        event.kind = "profile.ready"
    elif fault == "report":
        event.report_id = uuid4()
    elif fault == "reporter":
        event.account_id = uuid4()
    else:
        event.occurrence_key = "unrelated"
    with pytest.raises(RuntimeError, match="actual owned canonical"):
        report_detail_value(report, context, event)


@pytest.mark.parametrize("fault", ["naive", "range", "position"])
def test_search_window_aware_bounded_metadata_anchor_not_commit_token(fault: str) -> None:
    with pytest.raises(ValueError, match=r"timezone|interval|anchor"):
        invalid_window(fault)


def invalid_window(fault: str) -> None:
    if fault == "naive":
        OperatorReportFilters(submitted_from=NOW.replace(tzinfo=None))
    elif fault == "range":
        OperatorReportFilters(submitted_from=NOW, submitted_before=NOW)
    else:
        OperatorReportPosition(NOW, NOW + timedelta(seconds=1), uuid4())


def test_search_fingerprint_contains_only_bounded_filters_not_private_comment() -> None:
    filters = OperatorReportFilters(
        uuid4(), uuid4(), uuid4(), ReportCategory.SPAM, NOW - timedelta(days=1), NOW
    )
    parts = filters.fingerprint_parts()
    assert parts[1:4] == (str(filters.reporter_id), str(filters.target_id), str(filters.context_id))
    assert parts[4] == "spam"
    assert parts[-1] == NOW.isoformat()


def test_report_cursor_actor_grant_filter_resource_purpose_and_fixed_anchor_are_bound() -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    position = OperatorReportPosition(NOW, NOW - timedelta(seconds=1), uuid4())
    token = CODEC.encode_reports(scope, b"q" * 32, position)
    assert CODEC.decode_reports(scope, b"q" * 32, token, NOW) == position
    assert str(position.report_id) not in token
    for actor, digest in (
        (replace(scope, account_id=uuid4()), b"q" * 32),
        (replace(scope, access_version=2), b"q" * 32),
        (scope, b"x" * 32),
        (scope, b"bad"),
    ):
        with pytest.raises(InvalidOperatorCursorError):
            CODEC.decode_reports(actor, digest, token, NOW)
    other = FernetOperatorEventCursorCodec.from_key(b"r" * 32)
    alien = other.cipher.encrypt(b"[]").decode("ascii")
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_reports(scope, b"q" * 32, alien, NOW)
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_reports(scope, b"q" * 32, token, NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="32-byte"):
        FernetOperatorReportCursorCodec.from_key(b"bad")
    with pytest.raises(ValueError, match="actual query HMAC"):
        CODEC.encode_reports(scope, b"bad", position)


@pytest.mark.parametrize("fault", ["date", "naive", "position", "id"])
def test_valid_crypto_does_not_make_malformed_report_position_valid(fault: str) -> None:
    scope = OperatorCursorScope(uuid4(), 1)
    parts = [
        "operator-reports-v1",
        str(scope.account_id),
        str(scope.access_version),
        (b"q" * 32).hex(),
        NOW.isoformat(),
        NOW.isoformat(),
        str(uuid4()),
    ]
    if fault == "date":
        parts[4] = "not date"
    elif fault == "naive":
        parts[4] = NOW.replace(tzinfo=None).isoformat()
    elif fault == "position":
        parts[5] = (NOW + timedelta(seconds=1)).isoformat()
    else:
        parts[6] = "not id"
    token = CODEC.cipher.encrypt(json.dumps(parts).encode("ascii")).decode("ascii")
    with pytest.raises(InvalidOperatorCursorError):
        CODEC.decode_reports(scope, b"q" * 32, token, NOW)
