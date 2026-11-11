"""Bounded bulk selected-source loading. Never selects private support content."""

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.external_delivery.membership import membership_evidence
from studymate.domain.client_observations.events import PublicFrame
from studymate.domain.external_delivery.sources import (
    CanonicalSource,
    CapturedSource,
    CaptureMode,
    ClientObservationSource,
    MembershipEvidence,
    SelectedSource,
    SourceKind,
    SupportCaseSource,
)
from studymate.domain.notification_preferences.state import NotificationMode
from studymate.domain.operator.timeline import OperatorEventKind
from studymate.domain.support.cases import SupportTopic
from studymate.infrastructure.client_observations.models import (
    ClientObservationRecord,
    ObservationFrameRecord,
)
from studymate.infrastructure.client_observations.reads import read_observation
from studymate.infrastructure.external_delivery.models import (
    DeliverySourceRecord,
)
from studymate.infrastructure.notification_preferences.models import PreferenceRevisionRecord
from studymate.infrastructure.operator.timeline_values import event_value
from studymate.infrastructure.persistence.email_models import EmailChallengeRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.support.models import SupportCaseRecord

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class SelectedSourceLoader:
    session: AsyncSession

    async def load(self, sources: tuple[DeliverySourceRecord, ...]) -> tuple[CapturedSource, ...]:
        facts: dict[tuple[SourceKind, UUID], SelectedSource] = {}
        await self._canonical(sources, facts)
        await self._observations(sources, facts)
        support_ids = tuple(
            row.support_case_id for row in sources if row.support_case_id is not None
        )
        if support_ids:
            rows = (
                await self.session.execute(
                    select(
                        SupportCaseRecord.id,
                        SupportCaseRecord.actor_id,
                        SupportCaseRecord.topic,
                        SupportCaseRecord.received_at,
                    ).where(SupportCaseRecord.id.in_(support_ids))
                )
            ).all()
            for case_id, actor_id, topic, at in rows:
                facts[(SourceKind.SUPPORT_CASE, case_id)] = SupportCaseSource(
                    case_id, actor_id, SupportTopic(topic), at
                )
        result: list[CapturedSource] = []
        for row in sources:
            kind = SourceKind(row.source_kind)
            source_id = row.canonical_event_id or row.observation_id or row.support_case_id
            fact = facts.get((kind, source_id)) if source_id is not None else None
            if fact is None:
                raise RuntimeError("Captured external delivery source lost its actual FK target")
            result.append(
                CapturedSource(
                    row.id, kind, fact, CaptureMode(row.mode), row.captured_at, row.routing_version
                )
            )
        return tuple(result)

    async def _canonical(
        self,
        sources: tuple[DeliverySourceRecord, ...],
        facts: dict[tuple[SourceKind, UUID], SelectedSource],
    ) -> None:
        ids = tuple(row.canonical_event_id for row in sources if row.canonical_event_id is not None)
        if not ids:
            return
        rows = tuple(
            await self.session.scalars(
                select(ProductEventRecord).where(ProductEventRecord.id.in_(ids))
            )
        )
        confirmation_keys = tuple(
            (row.account_id, row.occurred_at) for row in rows if row.kind == "auth.email_confirmed"
        )
        consumed: set[tuple[UUID, datetime]] = set()
        if confirmation_keys:
            evidence = (
                await self.session.execute(
                    select(EmailChallengeRecord.account_id, EmailChallengeRecord.consumed_at)
                    .where(
                        tuple_(
                            EmailChallengeRecord.account_id, EmailChallengeRecord.consumed_at
                        ).in_(confirmation_keys)
                    )
                    .distinct()
                )
            ).all()
            consumed = {(owner, at) for owner, at in evidence if at is not None}
        preference_keys = tuple(
            (row.account_id, row.notification_preference_version)
            for row in rows
            if row.notification_preference_version is not None
        )
        preferences: dict[tuple[UUID, int], str] = {}
        if preference_keys:
            selected = (
                await self.session.execute(
                    select(
                        PreferenceRevisionRecord.account_id,
                        PreferenceRevisionRecord.version,
                        PreferenceRevisionRecord.mode,
                    ).where(
                        tuple_(
                            PreferenceRevisionRecord.account_id, PreferenceRevisionRecord.version
                        ).in_(preference_keys)
                    )
                )
            ).all()
            preferences = {(owner, version): mode for owner, version, mode in selected}
        for row in rows:
            projected = event_value(row)
            evidence_kind = (
                membership_evidence(
                    row.occurrence_key,
                    consumed_challenge_proven=(row.account_id, row.occurred_at) in consumed,
                )
                if projected.kind == OperatorEventKind.EMAIL_CONFIRMED
                else MembershipEvidence.NOT_APPLICABLE
            )
            mode = (
                preferences.get((row.account_id, row.notification_preference_version))
                if row.notification_preference_version is not None
                else None
            )
            facts[(SourceKind.CANONICAL, row.id)] = CanonicalSource(
                row.id,
                row.account_id,
                projected.kind,
                row.occurred_at,
                projected.facts,
                evidence_kind,
                NotificationMode(mode) if mode is not None else None,
            )

    async def _observations(
        self,
        sources: tuple[DeliverySourceRecord, ...],
        facts: dict[tuple[SourceKind, UUID], SelectedSource],
    ) -> None:
        ids = tuple(row.observation_id for row in sources if row.observation_id is not None)
        if not ids:
            return
        rows = tuple(
            await self.session.scalars(
                select(ClientObservationRecord).where(ClientObservationRecord.id.in_(ids))
            )
        )
        frame_rows = tuple(
            await self.session.scalars(
                select(ObservationFrameRecord)
                .where(ObservationFrameRecord.observation_id.in_(ids))
                .order_by(ObservationFrameRecord.observation_id, ObservationFrameRecord.frame_index)
            )
        )
        frames: dict[UUID, list[PublicFrame]] = {}
        for frame in frame_rows:
            frames.setdefault(frame.observation_id, []).append(
                PublicFrame(frame.asset_id, frame.line, frame.column_number)
            )
        for row in rows:
            facts[(SourceKind.CLIENT_OBSERVATION, row.id)] = ClientObservationSource(
                row.id,
                row.account_id,
                row.received_at,
                read_observation(row, tuple(frames.get(row.id, ()))),
                row.release_id,
            )
