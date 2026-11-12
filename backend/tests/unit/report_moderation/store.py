from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.report_moderation.ports import ReportReviewIntent
from studymate.domain.operator.profile_reports import OperatorReportKind
from studymate.domain.report_moderation.reviews import (
    REVIEW_HISTORY_PAGE_SIZE,
    ReportReviewRevision,
    ReviewReportSource,
)
from tests.unit.operator.store import TARGET, Store

REPORT_ID = UUID(int=7701)


class ReviewStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.report: ReviewReportSource | None = ReviewReportSource(
            REPORT_ID, OperatorReportKind.PROFILE, UUID(int=7702), TARGET, UUID(int=7703)
        )
        self.reviews: list[ReportReviewRevision] = []
        self.intents: dict[tuple[UUID, str], ReportReviewIntent] = {}
        self.events: list[UUID] = []
        self.fail_event = False
        self.fail_commit = False
        self.expire_after_write = False

    @asynccontextmanager
    async def transaction(
        self, actor_secret_digest: bytes | None = None, report_id: UUID | None = None
    ) -> AsyncIterator["ReviewStore"]:
        if actor_secret_digest is not None:
            assert actor_secret_digest
            assert report_id is not None
        before = (self.reviews.copy(), self.intents.copy(), self.events.copy())
        try:
            async with super().transaction():
                yield self
                if self.fail_commit:
                    raise RuntimeError("synthetic commit failure")
        except BaseException:
            self.reviews, self.intents, self.events = before
            raise

    async def lock_report(self, report_id: UUID) -> ReviewReportSource | None:
        self.queried()
        return self.report if self.report is not None and self.report.id == report_id else None

    async def latest_review(self, report_id: UUID) -> ReportReviewRevision | None:
        return next((row for row in reversed(self.reviews) if row.report_id == report_id), None)

    async def prior_review(self, actor_id: UUID, key: IntentKey) -> ReportReviewIntent | None:
        return self.intents.get((actor_id, key.value))

    async def append_review(
        self, source: ReportReviewRevision, key: IntentKey, fingerprint: bytes
    ) -> ReportReviewRevision:
        assert source.operator == self.access
        assert source.actor_session_id == self.actor.session.id
        self.reviews.append(source)
        self.events.append(source.event_id)
        if self.fail_event:
            raise RuntimeError("synthetic canonical failure")
        self.intents[(source.operator.account_id, key.value)] = ReportReviewIntent(
            fingerprint, source
        )
        if self.expire_after_write:
            self.clock = self.actor.session.expires_at
        return source

    async def review_history(
        self, report_id: UUID, anchor: int, before: int | None
    ) -> tuple[ReportReviewRevision, ...]:
        return tuple(
            row
            for row in reversed(self.reviews)
            if row.report_id == report_id
            and row.version <= anchor
            and (before is None or row.version < before)
        )[: REVIEW_HISTORY_PAGE_SIZE + 1]
