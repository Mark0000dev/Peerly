import json
from uuid import uuid4

import pytest

from studymate.application.operator.report_triage_evidence import (
    ReportedProfileText,
    ReportTriageEvidenceUnavailableError,
    report_triage_evidence,
)
from tests.unit.operator.profile_history_store import revision
from tests.unit.operator.report_store import report


def test_projection_keeps_only_actual_selected_profile_text_and_report_context() -> None:
    detail = report()
    raw = revision(detail.context.snapshot.profile_version, detail.report.target_id)
    profile = ReportedProfileText(raw.account_id, raw.version, raw.display_name, raw.about)
    evidence = report_triage_evidence(detail, profile=profile)
    decoded = json.loads(evidence)
    assert decoded["report_comment"] == detail.comment
    assert decoded["selected_item"]["display_name"] == profile.display_name
    assert decoded["selected_item"]["about"] == profile.about
    assert decoded["selected_item"]["image_pixels_included"] is False
    assert "programme" not in evidence
    assert "languages" not in evidence
    assert str(detail.report.reporter_id) not in evidence


def test_current_or_foreign_profile_cannot_replace_original_reported_revision() -> None:
    detail = report()
    for wrong in (revision(2, detail.report.target_id), revision(1, uuid4())):
        with pytest.raises(ReportTriageEvidenceUnavailableError):
            report_triage_evidence(
                detail,
                profile=ReportedProfileText(
                    wrong.account_id, wrong.version, wrong.display_name, wrong.about
                ),
            )
    with pytest.raises(ReportTriageEvidenceUnavailableError):
        report_triage_evidence(detail)


def test_oversized_retained_text_is_unavailable_without_truncation_or_invented_evidence() -> None:
    detail = report()
    profile = ReportedProfileText(detail.report.target_id, 1, "Name", "x" * 4001)
    with pytest.raises(ReportTriageEvidenceUnavailableError):
        report_triage_evidence(detail, profile=profile)
    assert profile.about == "x" * 4001
