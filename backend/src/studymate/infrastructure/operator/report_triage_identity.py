"""Full factual triage identity; explicit ordered locks, no fabricated omitted fields."""

from uuid import UUID

from sqlalchemy import Nullable, and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.identity.sessions import IdentitySnapshot
from studymate.domain.identity import Session, StudentEmail
from studymate.domain.membership import Membership
from studymate.infrastructure.persistence.email_models import EmailChallengeRecord
from studymate.infrastructure.persistence.identity_claims import identity_lineage_banned
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.onboarding_models import ProfileActivationRecord
from studymate.infrastructure.persistence.registration_reads import read_receipt


async def ordered_triage_accounts(
    session: AsyncSession, digest: bytes, target_id: UUID | None
) -> UUID | None:
    scope = (
        select(SessionRecord.account_id)
        .where(SessionRecord.secret_digest == digest)
        .scalar_subquery()
    )
    participants = AccountRecord.id == scope
    if target_id is not None:
        participants = or_(participants, AccountRecord.id == target_id)
    rows = tuple(
        (
            await session.execute(
                select(AccountRecord.id, Nullable(scope.label("actor_id")))
                .where(scope.is_not(None), participants)
                .order_by(AccountRecord.id)
                .with_for_update(key_share=True)
            )
        ).all()
    )
    if not rows:
        return None
    actor_id = rows[0][1]
    if actor_id is None or not any(row[0] == actor_id for row in rows):
        return None
    return actor_id


async def lock_triage_identity(
    session: AsyncSession, digest: bytes, target_id: UUID | None
) -> IdentitySnapshot | None:
    actor_id = await ordered_triage_accounts(session, digest, target_id)
    if actor_id is None:
        return None
    challenge = (
        select(EmailChallengeRecord.id)
        .where(
            EmailChallengeRecord.account_id == actor_id,
            EmailChallengeRecord.session_id == SessionRecord.id,
            EmailChallengeRecord.superseded_at.is_(None),
        )
        .order_by(EmailChallengeRecord.created_at.desc(), EmailChallengeRecord.id.desc())
        .limit(1)
        .correlate(SessionRecord)
        .scalar_subquery()
    )
    pending = case(
        (
            and_(
                InstitutionalBindingRecord.account_id.is_(None),
                AccountRecord.banned_at.is_(None),
                AccountRecord.deleted_at.is_(None),
            ),
            challenge,
        ),
        else_=None,
    )
    activation = (
        select(ProfileActivationRecord.account_id)
        .where(ProfileActivationRecord.account_id == actor_id)
        .exists()
    )
    row = (
        await session.execute(
            select(
                SessionRecord,
                AccountRecord,
                Nullable(InstitutionalBindingRecord),
                pending,
                activation,
            )
            .select_from(SessionRecord)
            .join(AccountRecord, AccountRecord.id == SessionRecord.account_id)
            .outerjoin(
                InstitutionalBindingRecord,
                InstitutionalBindingRecord.account_id == AccountRecord.id,
            )
            .where(SessionRecord.secret_digest == digest, SessionRecord.account_id == actor_id)
            .with_for_update(of=SessionRecord, key_share=True)
        )
    ).one_or_none()
    if row is None:
        return None
    stored, account, binding, pending_id, activated = row
    banned = account.banned_at is not None or await identity_lineage_banned(session, actor_id)
    registration = await read_receipt(session, actor_id)
    return IdentitySnapshot(
        session=Session(
            stored.id, stored.account_id, stored.issued_at, stored.expires_at, stored.revoked_at
        ),
        membership=Membership(StudentEmail(binding.email), binding.verified_at, binding.revoked_at)
        if binding is not None
        else None,
        banned=banned,
        deleted_at=account.deleted_at,
        registration=registration,
        email_challenge_id=pending_id,
        activation_complete=bool(activated),
    )
