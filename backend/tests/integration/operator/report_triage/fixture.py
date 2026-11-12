from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.idempotency import IntentKey
from studymate.application.operator.report_triage import (
    EnqueueReportTriage,
    EnqueueReportTriageCommand,
    ReadReportTriageContext,
)
from studymate.infrastructure.operator.report_triage_cursors import FernetReportTriageSourceCodec
from studymate.infrastructure.operator.report_triage_transactions import (
    SqlOperatorReportTriageUnitOfWork,
)
from studymate.infrastructure.persistence.product_events import (
    record_operator_audit,
    record_report_triage_submission,
)
from tests.integration.operator.test_reports import Reports, reports
from tests.integration.requests.fixture import FINGERPRINTER, HASHER

CODEC = FernetReportTriageSourceCodec.from_key(b"t" * 32)


@dataclass(frozen=True, slots=True)
class TriageCase:
    reports: Reports
    unit: SqlOperatorReportTriageUnitOfWork

    def enqueue(self) -> EnqueueReportTriage:
        return EnqueueReportTriage(self.unit, HASHER, FINGERPRINTER, CODEC)

    async def command(self, key: str = "operator-triage-proof") -> EnqueueReportTriageCommand:
        context = await ReadReportTriageContext(self.unit, HASHER, CODEC)(
            self.reports.owner.credential, self.reports.report.id
        )
        assert context is not None
        assert context.source_token is not None
        return EnqueueReportTriageCommand(
            self.reports.owner.credential,
            self.reports.report.id,
            context.source_token,
            IntentKey(key),
        )


async def prepared(engine: AsyncEngine) -> TriageCase:
    api = await reports(engine)
    return TriageCase(
        api,
        SqlOperatorReportTriageUnitOfWork(
            api.uow.sessions, record_operator_audit, record_report_triage_submission
        ),
    )
