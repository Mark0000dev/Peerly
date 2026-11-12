"""Finite retained report sources for privileged read acceptance, with real FKs."""

from collections.abc import Mapping
from datetime import timedelta
from uuid import UUID

from operator_retained_fixture import SOURCE_TIME, retained_id
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.report_models import (
    ProfileAccessRecord,
    ProfileReportRecord,
)

REPORT_COUNT = 53
RAW_COMMENT = (
    "Saved literal <script>alert('not executable')</script>\nOriginal report spacing"
)


async def seed_report_records(
    engine: AsyncEngine, namespace: str, targets: Mapping[str, str]
) -> dict[str, str]:
    reporter = UUID(targets["active_id"])
    target = UUID(targets["deleted_id"])
    at = SOURCE_TIME + timedelta(days=3)
    if namespace.split("/")[1] == "reports-empty":
        return {}
    async with async_sessionmaker(engine).begin() as session:
        for slot in range(REPORT_COUNT):
            context = retained_id(namespace, f"report-context/{slot}")
            report = retained_id(namespace, f"report/{slot}")
            rich = slot == REPORT_COUNT - 1
            session.add(
                ProfileAccessRecord(
                    id=context,
                    viewer_id=reporter,
                    target_id=target,
                    profile_version=1,
                    photo_version=1,
                    goal_id=None,
                    goal_version=None,
                    help_version=1,
                    issued_at=at + timedelta(seconds=slot),
                    request_id=retained_id(namespace, f"context-request/{slot}"),
                    action_id=None,
                    trace_id="1" * 32 if rich else None,
                    span_id="2" * 16 if rich else None,
                )
            )
            await session.flush()
            submitted = at + timedelta(minutes=slot + 1)
            session.add(
                ProfileReportRecord(
                    id=report,
                    reporter_id=reporter,
                    context_id=context,
                    category="other" if rich else "spam",
                    comment=RAW_COMMENT if rich else None,
                    submitted_at=submitted,
                )
            )
            await session.flush()
            # Slot0 is genuine retained legacy data without a recorded submission
            # event. Context provenance still exists and must not fill that gap.
            if slot > 0:
                session.add(
                    ProductEventRecord(
                        id=retained_id(namespace, f"report-event/{slot}"),
                        account_id=reporter,
                        kind="report.created",
                        occurrence_key=f"report:{report}",
                        schema_version=1,
                        occurred_at=submitted,
                        report_id=report,
                        request_id=retained_id(namespace, f"submission-request/{slot}")
                        if rich
                        else None,
                        action_id=None,
                        trace_id="3" * 32 if rich else None,
                        span_id="4" * 16 if rich else None,
                    )
                )
    return {
        "report_id": str(retained_id(namespace, "report/52")),
        "legacy_report_id": str(retained_id(namespace, "report/0")),
        "report_event_id": str(retained_id(namespace, "report-event/52")),
        "reporter_id": str(reporter),
        "report_target_id": str(target),
        "report_context_id": str(retained_id(namespace, "report-context/52")),
    }
