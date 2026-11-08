from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.sessions import StudentActionDeniedError, UnauthenticatedError
from studymate.application.safety.profile_reports import (
    ProfileReportPolicy,
    ProfileReportRateLimitedError,
    ProfileReportTransaction,
    ReportBudget,
    ReportContextUnavailableError,
    ReportIntent,
    SubmitProfileReport,
    SubmitProfileReportCommand,
)
from studymate.domain.reports import (
    ProfileAccessContext,
    ProfileReport,
    ProfileVersionRefs,
    ReportCategory,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, IdentityStore


class Store(IdentityStore):
    def __init__(self, *, expire_before_commit: bool = False) -> None:
        super().__init__()
        self.actor = replace(self.actor, activation_complete=True)
        context = ProfileAccessContext(
            UUID(int=3),
            self.actor.session.account_id,
            ProfileVersionRefs(UUID(int=99), 1, 1, None, None, None),
            self.clock,
        )
        self.contexts = {context.id: context}
        self.reports: dict[UUID, ProfileReport] = {}
        self.intents: dict[str, ReportIntent] = {}
        self.expire_before_commit = expire_before_commit

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[ProfileReportTransaction]:
        reports, intents = self.reports.copy(), self.intents.copy()
        try:
            yield self
        except BaseException:
            self.reports, self.intents = reports, intents
            raise

    async def report_intent(self, actor_id: UUID, key: IntentKey) -> ReportIntent | None:
        assert actor_id == self.actor.session.account_id
        return self.intents.get(key.value)

    async def own_report(self, actor_id: UUID, report_id: UUID) -> ProfileReport | None:
        report = self.reports.get(report_id)
        return report if report is not None and report.reporter_id == actor_id else None

    async def access_context(self, actor_id: UUID, context_id: UUID) -> ProfileAccessContext | None:
        assert actor_id == self.actor.session.account_id
        return self.contexts.get(context_id)

    async def report_budget(self, actor_id: UUID, since: datetime) -> ReportBudget:
        submitted = [
            report.submitted_at
            for report in self.reports.values()
            if report.reporter_id == actor_id and report.submitted_at > since
        ]
        return ReportBudget(len(submitted), min(submitted) if submitted else None)

    async def add_report(self, report: ProfileReport) -> None:
        self.reports[report.id] = report

    async def remember_report_intent(
        self,
        actor_id: UUID,
        key: IntentKey,
        intent: ReportIntent,
        at: datetime,
    ) -> None:
        assert actor_id == self.actor.session.account_id
        assert at == self.clock
        self.intents[key.value] = intent
        if self.expire_before_commit:
            self.clock = self.actor.session.expires_at


def service(store: Store, *, maximum: int = 10) -> SubmitProfileReport:
    return SubmitProfileReport(
        store,
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes(range(32))),
        ProfileReportPolicy(maximum),
    )


def command() -> SubmitProfileReportCommand:
    return SubmitProfileReportCommand(
        CREDENTIAL,
        UUID(int=3),
        ReportCategory.SPAM,
        IntentKey("synthetic-intent"),
        "  Private comment  ",
    )


async def test_report_is_owned_normalized_and_replays_original_without_spending_budget() -> None:
    store = Store()
    submit = service(store, maximum=1)
    first = await submit(command())
    assert first.reporter_id == store.actor.session.account_id
    assert first.comment == "Private comment"
    assert await submit(replace(command(), comment="Private comment")) == first
    assert len(store.reports) == 1
    with pytest.raises(IdempotencyConflictError):
        await submit(replace(command(), comment="Different comment"))
    with pytest.raises(ProfileReportRateLimitedError) as limited:
        await submit(replace(command(), intent_key=IntentKey(str(uuid4()))))
    assert limited.value.retry_at == first.submitted_at + submit.policy.interval


@pytest.mark.parametrize("foreign", [True, False])
async def test_foreign_or_unknown_access_context_cannot_create_a_report(foreign: bool) -> None:
    store = Store()
    context = store.contexts[UUID(int=3)]
    if foreign:
        store.contexts[context.id] = replace(context, viewer_id=UUID(int=100))
    else:
        store.contexts.clear()
    with pytest.raises(ReportContextUnavailableError):
        await service(store)(command())
    assert store.reports == {}
    assert store.intents == {}


async def test_session_expiry_before_commit_rolls_back_report_and_original_result() -> None:
    store = Store(expire_before_commit=True)
    with pytest.raises(UnauthenticatedError):
        await service(store)(command())
    assert store.reports == {}
    assert store.intents == {}


@pytest.mark.parametrize("state", ["unverified", "banned", "deleted", "unactivated"])
async def test_report_never_bypasses_live_verified_activated_actor(state: str) -> None:
    store = Store()
    store.actor = replace(
        store.actor,
        membership=None if state == "unverified" else store.actor.membership,
        banned=state == "banned",
        deleted_at=store.clock if state == "deleted" else None,
        activation_complete=state != "unactivated",
    )
    with pytest.raises(UnauthenticatedError if state == "deleted" else StudentActionDeniedError):
        await service(store)(command())
    assert store.reports == {}


async def test_missing_retained_report_is_not_silently_replaced_with_another_submission() -> None:
    store = Store()
    submit = service(store)
    await submit(command())
    store.reports.clear()
    with pytest.raises(RuntimeError, match="unavailable"):
        await submit(command())
