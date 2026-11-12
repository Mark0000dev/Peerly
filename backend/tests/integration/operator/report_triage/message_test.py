import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.operator.report_triage import (
    EnqueueReportTriage,
    EnqueueReportTriageCommand,
    ReadReportTriageContext,
)
from studymate.domain.ai.tasks import TriageReport
from studymate.infrastructure.ai.codec import TASK_CODEC
from studymate.infrastructure.ai.models import AiJobRecord
from studymate.infrastructure.operator.report_triage_models import ReportTriageEvidenceRecord
from studymate.infrastructure.operator.report_triage_transactions import (
    SqlOperatorReportTriageUnitOfWork,
)
from studymate.infrastructure.persistence.product_events import (
    record_operator_audit,
    record_report_triage_submission,
)
from tests.integration.operator.report_triage.fixture import CODEC
from tests.integration.operator.test_reads import operator
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.safety.message_reports.fixture import prepared

pytestmark = pytest.mark.integration


async def test_actual_selected_message_caption_and_metadata_never_claim_image_analysis(
    ai_engine: AsyncEngine,
) -> None:
    api = await prepared(ai_engine)
    report = await api.submit()(api.command())
    viewer = await operator(ai_engine)
    unit = SqlOperatorReportTriageUnitOfWork(
        api.uow.sessions, record_operator_audit, record_report_triage_submission
    )
    context = await ReadReportTriageContext(unit, HASHER, CODEC)(viewer.credential, report.id)
    assert context is not None
    assert context.source_token is not None
    await EnqueueReportTriage(unit, HASHER, FINGERPRINTER, CODEC)(
        EnqueueReportTriageCommand(
            viewer.credential, report.id, context.source_token, IntentKey("image-caption-triage")
        )
    )
    async with unit.sessions() as session:
        source = (await session.scalars(select(ReportTriageEvidenceRecord))).one()
        assert source.report_kind == "message_image"
        assert source.profile_context_id is None
        assert source.message_context_id == report.context.id
        assert source.reporter_id == report.reporter_id
        assert source.target_id == api.chat.sender.id
        stored = (await session.scalars(select(AiJobRecord))).one()
        task = TASK_CODEC.validate_json(stored.input_json)
        assert isinstance(task, TriageReport)
        decoded = json.loads(task.evidence)
        assert decoded["selected_item"]["message_text"] == "Private image caption"
        assert decoded["selected_item"]["image_pixels_included"] is False
        assert decoded["report_comment"] == report.comment
        assert "storage_key" not in task.evidence
        assert "conversation_history" not in task.evidence
