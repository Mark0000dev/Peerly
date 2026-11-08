"""Same-transaction lifecycle effects; retained originals are never purged.

Login flows in the current schema are unbound until callback resolution. Their
source/IP digests are not account ownership, so they are not reassigned here.
The callback's existing deleted-identity guard denies later session creation.
Already in-flight external delivery/execution is not claimed to be recalled.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.lifecycle.intents import LifecycleResult
from studymate.domain.lifecycle.states import DeletionTransition
from studymate.infrastructure.ai.persistence import cancel_actor_jobs
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
)
from studymate.infrastructure.persistence.identity_models import SessionRecord
from studymate.infrastructure.persistence.product_events import (
    record_account_lifecycle,
    record_request_outcome,
)
from studymate.infrastructure.requests.lifecycle import close_actor_requests


async def _stop_verification(session: AsyncSession, account_id: UUID, at: datetime) -> None:
    await session.execute(
        update(EmailChallengeRecord)
        .where(
            EmailChallengeRecord.account_id == account_id,
            EmailChallengeRecord.consumed_at.is_(None),
            EmailChallengeRecord.superseded_at.is_(None),
        )
        .values(superseded_at=at, code_digest=None)
    )
    await session.execute(
        update(EmailDeliveryRecord)
        .where(
            EmailDeliveryRecord.challenge_id.in_(
                select(EmailChallengeRecord.id).where(EmailChallengeRecord.account_id == account_id)
            ),
            EmailDeliveryRecord.status.in_(("queued", "inflight")),
        )
        .values(status="cancelled", sealed_envelope=None, lease_until=None)
    )


async def apply_lifecycle_effects(session: AsyncSession, transition: LifecycleResult) -> None:
    source = transition.revision
    if source is None:
        raise ValueError("A no-op cannot apply new lifecycle effects")
    account_id = transition.after.account_id
    if isinstance(transition, DeletionTransition):
        at = transition.revision.deleted_at
        await session.execute(
            update(SessionRecord)
            .where(SessionRecord.account_id == account_id, SessionRecord.revoked_at.is_(None))
            .values(revoked_at=at)
        )
        await _stop_verification(session, account_id, at)
        await cancel_actor_jobs(session, account_id)
        await close_actor_requests(session, account_id, account_id, record_request_outcome)
    elif transition.revision is not None and transition.revision.banned:
        await _stop_verification(session, account_id, transition.revision.changed_at)
        await cancel_actor_jobs(session, account_id)
        await close_actor_requests(session, account_id, None, record_request_outcome)
    await record_account_lifecycle(session, transition)
