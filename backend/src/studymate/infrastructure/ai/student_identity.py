"""Full locked student identity in two roundtrips; no permission or source field omitted."""

from typing import TYPE_CHECKING

from sqlalchemy import Nullable, and_, case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from studymate.application.identity.sessions import IdentitySnapshot
from studymate.domain.identity import Session, StudentEmail
from studymate.domain.membership import Membership
from studymate.infrastructure.persistence.email_models import EmailChallengeRecord
from studymate.infrastructure.persistence.identity_claims import identity_lineage_ban_statement
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.onboarding_models import ProfileActivationRecord
from studymate.infrastructure.persistence.registration_models import (
    PolicyDocumentRecord,
    RegistrationContextRecord,
    RegistrationReceiptRecord,
)
from studymate.infrastructure.persistence.registration_reads import (
    context_from_record,
    receipt_from_records,
)

if TYPE_CHECKING:
    from studymate.domain.registration import RegistrationReceipt


async def lock_student_identity(session: AsyncSession, digest: bytes) -> IdentitySnapshot | None:
    scope = (
        select(SessionRecord.account_id)
        .where(SessionRecord.secret_digest == digest)
        .scalar_subquery()
    )
    accounts = (
        select(AccountRecord.id)
        .where(scope.is_not(None), AccountRecord.id == scope)
        .order_by(AccountRecord.id)
        .with_for_update(key_share=True)
        .cte("student_identity_account_locks")
        .prefix_with("MATERIALIZED")
    )
    # Session LockRows depends on materialized already-locked accounts. Factual
    # lineage/registration reads are a SECOND statement, after every lock wait.
    actor_id = await session.scalar(
        select(SessionRecord.account_id)
        .select_from(SessionRecord)
        .join(accounts, accounts.c.id == SessionRecord.account_id)
        .where(SessionRecord.secret_digest == digest)
        .with_for_update(of=SessionRecord, key_share=True)
    )
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
    terms, privacy = aliased(PolicyDocumentRecord), aliased(PolicyDocumentRecord)
    row = (
        await session.execute(
            select(
                SessionRecord,
                AccountRecord,
                Nullable(InstitutionalBindingRecord),
                pending,
                activation,
                or_(
                    AccountRecord.banned_at.is_not(None),
                    identity_lineage_ban_statement(actor_id).scalar_subquery(),
                ),
                Nullable(RegistrationReceiptRecord),
                Nullable(RegistrationContextRecord),
                Nullable(terms.version),
                Nullable(terms.published_at),
                Nullable(privacy.version),
                Nullable(privacy.published_at),
            )
            .select_from(SessionRecord)
            .join(AccountRecord, AccountRecord.id == SessionRecord.account_id)
            .outerjoin(
                InstitutionalBindingRecord,
                InstitutionalBindingRecord.account_id == AccountRecord.id,
            )
            .outerjoin(
                RegistrationReceiptRecord, RegistrationReceiptRecord.account_id == AccountRecord.id
            )
            .outerjoin(
                RegistrationContextRecord,
                RegistrationContextRecord.id == RegistrationReceiptRecord.context_id,
            )
            .outerjoin(terms, terms.id == RegistrationContextRecord.terms_id)
            .outerjoin(privacy, privacy.id == RegistrationContextRecord.privacy_id)
            .where(SessionRecord.secret_digest == digest, SessionRecord.account_id == actor_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if row is None:
        return None
    (
        stored,
        account,
        binding,
        pending_id,
        activated,
        banned,
        receipt,
        context,
        terms_version,
        terms_published,
        privacy_version,
        privacy_published,
    ) = row
    registration: RegistrationReceipt | None = None
    if receipt is not None:
        if (
            context is None
            or terms_version is None
            or terms_published is None
            or privacy_version is None
            or privacy_published is None
        ):
            raise RuntimeError("Stored registration lost its actual context or policy source")
        registration = receipt_from_records(
            receipt,
            context_from_record(
                context, terms_version, terms_published, privacy_version, privacy_published
            ),
        )
    return IdentitySnapshot(
        session=Session(
            stored.id, stored.account_id, stored.issued_at, stored.expires_at, stored.revoked_at
        ),
        membership=Membership(StudentEmail(binding.email), binding.verified_at, binding.revoked_at)
        if binding is not None
        else None,
        banned=bool(banned),
        deleted_at=account.deleted_at,
        registration=registration,
        email_challenge_id=pending_id,
        activation_complete=bool(activated),
    )
