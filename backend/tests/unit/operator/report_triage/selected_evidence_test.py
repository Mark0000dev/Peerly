"""Pure retained-row projection controls; not a PostgreSQL or lock substitute."""

import json
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from studymate.application.operator.report_triage_evidence import ReportedProfileText
from studymate.domain.operator.profile_reports import OperatorReportKind
from studymate.domain.report_moderation.reviews import ReviewReportSource
from studymate.infrastructure.operator.report_triage_sources import (
    SelectedReportRows,
    selected_report_evidence,
)
from studymate.infrastructure.persistence.message_models import MessageRecord
from studymate.infrastructure.persistence.message_report_models import MessageReportContextRecord
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportRecord,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.report_store import report

IMAGE_VERSION = 2


def profile_rows() -> tuple[ReviewReportSource, SelectedReportRows]:
    detail = report()
    reference = detail.context.snapshot
    context = ProfileAccessRecord(
        id=detail.context.id,
        viewer_id=detail.report.reporter_id,
        target_id=reference.account_id,
        profile_version=reference.profile_version,
        photo_version=reference.photo_version,
        goal_id=reference.goal_id,
        goal_version=reference.goal_version,
        help_version=reference.help_version,
        issued_at=detail.context.issued_at,
        request_id=None,
        action_id=None,
        trace_id=None,
        span_id=None,
    )
    record = ProfileReportRecord(
        id=detail.report.id,
        reporter_id=detail.report.reporter_id,
        kind="profile",
        context_id=context.id,
        message_context_id=None,
        category=detail.report.category.value,
        comment=detail.comment,
        submitted_at=detail.report.submitted_at,
    )
    source = ReviewReportSource(
        record.id, OperatorReportKind.PROFILE, record.reporter_id, context.target_id, context.id
    )
    return source, SelectedReportRows(
        record,
        context,
        None,
        None,
        ReportedProfileText(
            reference.account_id,
            reference.profile_version,
            "Retained selected name",
            "Retained selected about",
        ),
    )


def image_rows() -> tuple[ReviewReportSource, SelectedReportRows]:
    viewer, author = UUID(int=10), UUID(int=20)
    message = MessageRecord(
        id=uuid4(),
        operation_id=uuid4(),
        conversation_id=uuid4(),
        low_id=viewer,
        high_id=author,
        author_id=author,
        client_message_id=uuid4(),
        state="confirmed",
        sequence=1,
        text="Only selected image caption",
        image_id=uuid4(),
        image_version=IMAGE_VERSION,
        image_attempt_id=uuid4(),
        image_state="ready",
        sent_at=NOW,
    )
    context = MessageReportContextRecord(
        id=uuid4(),
        viewer_id=viewer,
        message_id=message.id,
        conversation_id=message.conversation_id,
        low_id=viewer,
        high_id=author,
        target_id=author,
        client_message_id=message.client_message_id,
        image_id=message.image_id,
        image_version=message.image_version,
        image_attempt_id=message.image_attempt_id,
        image_state="ready",
        issued_at=NOW,
        request_id=None,
        action_id=None,
        trace_id=None,
        span_id=None,
    )
    record = ProfileReportRecord(
        id=uuid4(),
        reporter_id=viewer,
        kind="message_image",
        context_id=None,
        message_context_id=context.id,
        category="spam",
        comment="Selected report comment",
        submitted_at=NOW,
    )
    source = ReviewReportSource(
        record.id, OperatorReportKind.MESSAGE_IMAGE, viewer, author, context.id
    )
    return source, SelectedReportRows(record, None, context, message, None)


def test_profile_mapping_preserves_original_selected_version_and_closed_fields() -> None:
    source, rows = profile_rows()
    evidence = selected_report_evidence(source, rows)
    assert evidence is not None
    selected = json.loads(evidence)["selected_item"]
    assert selected == {
        "display_name": "Retained selected name",
        "about": "Retained selected about",
        "profile_version": 1,
        "photo_version": 1,
        "image_pixels_included": False,
    }
    assert "programme" not in evidence
    assert "languages" not in evidence
    assert str(source.reporter_id) not in evidence
    assert "Retained selected" not in repr(rows)


@pytest.mark.parametrize("change", ["missing", "foreign", "newer", "oversized"])
def test_unrepresentable_profile_remains_manual_without_fabricated_evidence(change: str) -> None:
    source, rows = profile_rows()
    assert rows.profile is not None
    original = rows.profile
    profile: ReportedProfileText | None = original
    if change == "missing":
        profile = None
    elif change == "foreign":
        profile = replace(original, account_id=uuid4())
    elif change == "newer":
        profile = replace(original, version=2)
    else:
        profile = replace(original, about="x" * 4001)
    assert selected_report_evidence(source, replace(rows, profile=profile)) is None


@pytest.mark.parametrize("change", ["id", "kind", "target", "context"])
def test_wrong_locked_source_is_rejected_before_any_evidence_return(change: str) -> None:
    source, rows = profile_rows()
    if change == "id":
        source = replace(source, id=uuid4())
    elif change == "kind":
        source = replace(source, kind=OperatorReportKind.MESSAGE_IMAGE)
    elif change == "target":
        source = replace(source, target_id=uuid4())
    else:
        source = replace(source, context_id=uuid4())
    with pytest.raises(RuntimeError, match="differs from actual locked report/evidence"):
        selected_report_evidence(source, rows)


def test_image_mapping_keeps_selected_caption_and_attachment_without_history_or_pixels() -> None:
    source, rows = image_rows()
    evidence = selected_report_evidence(source, rows)
    assert evidence is not None
    assert rows.message is not None
    selected = json.loads(evidence)["selected_item"]
    assert selected["message_text"] == rows.message.text
    assert selected["image_id"] == str(rows.message.image_id)
    assert selected["image_version"] == IMAGE_VERSION
    assert selected["image_pixels_included"] is False
    assert "conversation_history" not in evidence
    assert "conversation_id" not in evidence
    assert "Only selected" not in repr(rows)


@pytest.mark.parametrize("change", ["image", "version", "attempt"])
def test_image_attachment_fk_mismatch_is_never_projected(change: str) -> None:
    source, rows = image_rows()
    assert rows.message is not None
    if change == "image":
        rows.message.image_id = uuid4()
    elif change == "version":
        rows.message.image_version = 3
    else:
        rows.message.image_attempt_id = uuid4()
    with pytest.raises(RuntimeError, match="differs from its actual message FK"):
        selected_report_evidence(source, rows)


@pytest.mark.parametrize("change", ["message", "conversation", "client", "author"])
def test_message_provenance_mismatch_is_unavailable_not_substituted(change: str) -> None:
    source, rows = image_rows()
    assert rows.message is not None
    if change == "message":
        rows.message.id = uuid4()
    elif change == "conversation":
        rows.message.conversation_id = uuid4()
    elif change == "client":
        rows.message.client_message_id = uuid4()
    else:
        rows.message.author_id = rows.message.low_id
    assert selected_report_evidence(source, rows) is None


def test_missing_retained_context_remains_an_integrity_error() -> None:
    source, rows = profile_rows()
    with pytest.raises(RuntimeError, match="actual profile-only retained context"):
        selected_report_evidence(source, replace(rows, profile_context=None))
