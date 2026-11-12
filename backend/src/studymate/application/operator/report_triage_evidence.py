"""Closed server projection of the selected reported item; never whole-conversation lookup."""

import json
from dataclasses import dataclass, field
from uuid import UUID

from studymate.domain.ai.tasks import MAX_EVIDENCE
from studymate.domain.messaging import ConfirmedMessage
from studymate.domain.operator.profile_reports import (
    OperatorProfileReportDetail,
    OperatorReportDetail,
)


@dataclass(frozen=True, slots=True)
class ReportedProfileText:
    account_id: UUID
    version: int
    display_name: str | None = field(repr=False)
    about: str | None = field(repr=False)


class ReportTriageEvidenceUnavailableError(Exception):
    pass


def report_triage_evidence(
    detail: OperatorReportDetail,
    *,
    profile: ReportedProfileText | None = None,
    message: ConfirmedMessage | None = None,
) -> str:
    selected: dict[str, str | int | bool | None]
    if isinstance(detail, OperatorProfileReportDetail):
        reference = detail.context.snapshot
        if (
            profile is None
            or message is not None
            or profile.account_id != reference.account_id
            or profile.version != reference.profile_version
        ):
            raise ReportTriageEvidenceUnavailableError
        selected = {
            "display_name": profile.display_name,
            "about": profile.about,
            "profile_version": profile.version,
            "photo_version": reference.photo_version,
            "image_pixels_included": False,
        }
    else:
        source = detail.context.source
        if (
            message is None
            or profile is not None
            or message.id != source.message_id
            or message.conversation_id != source.conversation_id
            or message.pair != source.pair
            or message.author_id != source.author_id
            or message.client_message_id != source.client_message_id
            or message.sent_at != source.sent_at
            or source.image is None
            or message.content.image_id != source.image.id
        ):
            raise ReportTriageEvidenceUnavailableError
        selected = {
            "message_text": message.content.text,
            "image_id": str(source.image.id),
            "image_version": source.image.version,
            "image_attempt_id": str(source.image.attempt_id),
            "image_pixels_included": False,
        }
    evidence = json.dumps(
        {
            "report_kind": detail.report.kind.value,
            "category": detail.report.category.value,
            "report_comment": detail.comment,
            "selected_item": selected,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(evidence) > MAX_EVIDENCE:
        raise ReportTriageEvidenceUnavailableError
    return evidence
