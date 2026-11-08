"""Existing report reads distinguish retained message evidence from profile snapshots."""

from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from studymate.domain.message_reports import MessageImageRef, ReportMessageSource
from studymate.domain.operator.profile_reports import (
    OperatorMessageImageReportContext,
    OperatorMessageImageReportDetail,
    OperatorProfileReportSummary,
    OperatorReportKind,
)
from studymate.domain.operator.timeline import OperatorEventOrigin
from studymate.domain.relationships import AccountPair
from studymate.domain.reports import ReportCategory
from studymate.infrastructure.operator.report_values import ReportListSource, report_detail_value
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.report_models import ProfileReportRecord
from studymate.presentation.operator.report_models import (
    OperatorReportDetailResponse,
    report_detail_response,
)
from tests.unit.identity_store import NOW


def detail() -> OperatorMessageImageReportDetail:
    reporter, target = UUID(int=2), UUID(int=3)
    source = ReportMessageSource(
        uuid4(),
        uuid4(),
        AccountPair.between(reporter, target),
        target,
        uuid4(),
        NOW,
        MessageImageRef(uuid4(), 2, uuid4()),
    )
    context = OperatorMessageImageReportContext(uuid4(), reporter, source, NOW - timedelta(days=1))
    summary = OperatorProfileReportSummary(
        uuid4(),
        reporter,
        target,
        context.id,
        ReportCategory.OTHER,
        NOW - timedelta(days=2),
        True,
        OperatorReportKind.MESSAGE_IMAGE,
    )
    return OperatorMessageImageReportDetail(
        summary, context, OperatorEventOrigin(), " Exact retained private report comment "
    )


def test_message_report_retains_original_timestamps_comment_and_tagged_context() -> None:
    value = detail()
    assert value.report.submitted_at < value.context.issued_at
    assert value.context.issued_at < value.context.source.sent_at
    response = report_detail_response(value)
    data = response.model_dump(mode="json")
    assert data["report"]["kind"] == "message_image"
    assert data["context"]["kind"] == "message_image"
    assert data["context"]["message_id"] == str(value.context.source.message_id)
    assert data["comment"] == value.comment
    for forbidden in ("profile_version", "photo_version", "source_sha256", "display_url", "text"):
        assert forbidden not in data["context"]
    assert value.comment is not None
    assert value.comment not in repr(value)
    assert value.comment not in repr(response)
    data["context"].pop("kind")
    with pytest.raises(ValidationError, match="discriminator"):
        OperatorReportDetailResponse.model_validate(data)


@pytest.mark.parametrize("fault", ["kind", "context", "comment", "other", "peer"])
def test_image_report_detail_rejects_mismatched_retained_evidence(fault: str) -> None:
    value = detail()
    with pytest.raises(ValueError, match=r"report|context|comment|Other"):
        invalid(value, fault)


def invalid(value: OperatorMessageImageReportDetail, fault: str) -> None:
    if fault == "kind":
        replace(value, report=replace(value.report, kind=OperatorReportKind.PROFILE))
    elif fault == "context":
        replace(value, context=replace(value.context, id=uuid4()))
    elif fault == "comment":
        replace(value, report=replace(value.report, has_comment=False))
    elif fault == "other":
        replace(value, comment=None, report=replace(value.report, has_comment=False))
    else:
        replace(value.context, reporter_id=value.context.source.author_id)


@pytest.mark.parametrize("kind", [OperatorReportKind.PROFILE, OperatorReportKind.MESSAGE_IMAGE])
def test_list_metadata_requires_actual_nonnullable_owned_evidence(kind: OperatorReportKind) -> None:
    value = detail().report
    row = ReportListSource(
        value.id,
        value.reporter_id,
        kind.value,
        value.category.value,
        value.submitted_at,
        True,
        value.context_id,
        value.target_id,
    )
    assert row.value().kind == kind
    with pytest.raises(RuntimeError, match="owned context"):
        replace(row, context_id=None).value()


def test_message_detail_maps_actual_owned_context_without_profile_placeholders() -> None:
    value = detail()
    source = value.context.source
    assert source.image is not None
    context = MessageReportContextRecord(
        id=value.context.id,
        viewer_id=value.report.reporter_id,
        target_id=value.report.target_id,
        conversation_id=source.conversation_id,
        low_id=source.pair.low,
        high_id=source.pair.high,
        message_id=source.message_id,
        client_message_id=source.client_message_id,
        image_id=source.image.id,
        image_version=source.image.version,
        image_attempt_id=source.image.attempt_id,
        issued_at=value.context.issued_at,
    )
    root = ProfileReportRecord(
        id=value.report.id,
        reporter_id=value.report.reporter_id,
        kind="message_image",
        context_id=None,
        message_context_id=context.id,
        category=value.report.category.value,
        submitted_at=value.report.submitted_at,
        comment=value.comment,
    )
    assert report_detail_value(root, None, None, context, source.sent_at) == value
    with pytest.raises(RuntimeError, match="message-only"):
        report_detail_value(root, None, None)
