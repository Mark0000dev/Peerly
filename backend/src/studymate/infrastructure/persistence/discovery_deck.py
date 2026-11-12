from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.discovery.cursors import DiscoveryCursor, DiscoveryView
from studymate.application.discovery.deck import DISCOVERY_PAGE_SIZE, CandidateSource
from studymate.application.discovery.profiles import DiscoveryProfileSource
from studymate.application.profiles.onboarding import ProfileSetupSnapshot
from studymate.domain.discovery_context import DiscoveryContext
from studymate.domain.discovery_freshness import DiscoveryExposure
from studymate.domain.discovery_order import DiscoveryPosition
from studymate.domain.discovery_passes import PrivatePassRevision
from studymate.domain.identity import StudentEmail
from studymate.domain.media import PhotoRevision
from studymate.domain.membership import Membership
from studymate.domain.onboarding import ProfileLifecycle
from studymate.domain.profiles import (
    DisplayName,
    OnboardingTask,
    ProfileBasics,
    ProfileRevision,
)
from studymate.infrastructure.observability.tracing import record_discovery_query
from studymate.infrastructure.persistence.discovery_pass_models import (
    DiscoveryContextRecord,
    DiscoveryDecisionHeadRecord,
    PrivatePassRecord,
    PrivatePassRevisionRecord,
)
from studymate.infrastructure.persistence.discovery_profiles import SqlDiscoveryProfileReader
from studymate.infrastructure.persistence.discovery_query import DiscoveryQuery
from studymate.infrastructure.persistence.goals import goal_value
from studymate.infrastructure.persistence.profile_sources import (
    read_help_versions,
    read_profile_languages,
)
from studymate.infrastructure.persistence.transactions import open_transaction


def _private_pass_query(context: DiscoveryContext) -> Select[PrivatePassRevisionRecord]:
    return (
        select(PrivatePassRevisionRecord)
        .join(
            PrivatePassRecord,
            (PrivatePassRecord.id == PrivatePassRevisionRecord.pass_id)
            & (PrivatePassRecord.current_version == PrivatePassRevisionRecord.version),
        )
        .join(DiscoveryContextRecord, DiscoveryContextRecord.id == PrivatePassRecord.context_id)
        .where(
            DiscoveryContextRecord.account_id == context.account_id,
            DiscoveryContextRecord.mode == context.mode.value,
            DiscoveryContextRecord.goal_id == context.goal_id,
            DiscoveryContextRecord.goal_version == context.goal_version,
            DiscoveryContextRecord.help_version == context.help_version,
        )
    )


def _pass_value(
    record: PrivatePassRevisionRecord, context: DiscoveryContext
) -> PrivatePassRevision:
    if record.account_id != context.account_id:
        raise RuntimeError("Private decision projection belongs to another actor")
    return PrivatePassRevision(
        record.pass_id,
        context,
        record.target_id,
        record.version,
        record.passed,
        record.decision_sequence,
        record.changed_at,
    )


@dataclass(frozen=True, slots=True)
class SqlDiscoveryDeckTransaction(SqlDiscoveryProfileReader):
    async def latest_undo_pass(self, context: DiscoveryContext) -> PrivatePassRevision | None:
        record = await self.session.scalar(
            _private_pass_query(context)
            .join(
                DiscoveryDecisionHeadRecord,
                (DiscoveryDecisionHeadRecord.account_id == PrivatePassRevisionRecord.account_id)
                & (
                    DiscoveryDecisionHeadRecord.last_sequence
                    == PrivatePassRevisionRecord.decision_sequence
                ),
            )
            .where(PrivatePassRevisionRecord.passed.is_(True))
        )
        return _pass_value(record, context) if record is not None else None

    async def candidates(
        self,
        context: DiscoveryContext,
        view: DiscoveryView,
        cursor: DiscoveryCursor | None,
        as_of: datetime,
        limit: int,
    ) -> tuple[CandidateSource, ...]:
        if not 1 <= limit <= DISCOVERY_PAGE_SIZE + 1:
            raise ValueError("Discovery SQL page must stay within its bounded limit")
        now = await self.now()
        query = DiscoveryQuery(context, view, as_of, now, cursor)
        rows = (await self.session.execute(query.statement(limit))).all()
        record_discovery_query(context.mode, view, tuple(row[1].account_id for row in rows))
        if not rows:
            return ()
        profiles = tuple(row[1] for row in rows)
        languages = await read_profile_languages(self.session, profiles)
        helpers = await read_help_versions(
            self.session, tuple((row[1].account_id, row[9]) for row in rows if row[9] is not None)
        )
        private_passes = {
            revision.target_id: _pass_value(revision, context)
            for revision in await self.session.scalars(
                _private_pass_query(context).where(
                    PrivatePassRevisionRecord.target_id.in_(
                        tuple(record.account_id for record in profiles)
                    )
                )
            )
        }
        candidates: list[CandidateSource] = []
        for (
            binding,
            profile,
            photo,
            goal,
            goal_revision,
            lifecycle,
            exposure,
            topic,
            freshness,
            _help_version,
        ) in rows:
            account_id = profile.account_id
            saved_profile = ProfileRevision(
                account_id,
                profile.version,
                ProfileBasics(
                    DisplayName(profile.display_name) if profile.display_name is not None else None,
                    profile.about,
                    profile.programme,
                    profile.year_label,
                    languages.get(account_id, ()),
                ),
                OnboardingTask(profile.task),
                profile.saved_at,
            )
            setup = ProfileSetupSnapshot(
                account_id,
                saved_profile,
                PhotoRevision(account_id, photo.version, photo.upload_id, photo.saved_at),
                goal_value(goal, goal_revision)
                if goal is not None and goal_revision is not None
                else None,
                helpers.get(account_id),
                ProfileLifecycle(
                    account_id,
                    lifecycle.completed_at,
                    lifecycle.version,
                    lifecycle.hidden_at,
                    lifecycle.changed_at,
                ),
                DiscoveryExposure(
                    account_id,
                    exposure.last_activity_at,
                    exposure.confirmed_at,
                    exposure.paused_at,
                    timedelta(seconds=exposure.inactivity_seconds),
                ),
            )
            source = DiscoveryProfileSource(
                setup,
                Membership(StudentEmail(binding.email), binding.verified_at, binding.revoked_at),
                True,
                False,
                False,
            )
            # Lifecycle booleans are source facts constrained by the same joined SQL row.
            candidates.append(
                CandidateSource(
                    source,
                    DiscoveryPosition(topic, freshness, account_id),
                    private_passes.get(account_id),
                )
            )
        return tuple(candidates)

    async def has_context_people(self, context: DiscoveryContext, at: datetime) -> bool:
        statement = DiscoveryQuery(context, DiscoveryView.CANDIDATES, at, at).statement(
            1, include_decisions=False
        )
        return bool(await self.session.scalar(select(statement.order_by(None).exists())))


@dataclass(frozen=True, slots=True)
class SqlDiscoveryDeckUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[SqlDiscoveryDeckTransaction]:
        async with open_transaction(self.sessions, read_only=True) as session:
            yield SqlDiscoveryDeckTransaction(session, shared_identity_locks=True)
