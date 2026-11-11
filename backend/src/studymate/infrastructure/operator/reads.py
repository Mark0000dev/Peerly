"""Raw stored operator projections; no student visibility/membership policy or secrets."""

from uuid import UUID

from sqlalchemy import Nullable, Select, and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.operator.data import (
    OperatorAccountSummary,
    OperatorMembershipSnapshot,
    OperatorRegistrationSnapshot,
    StoredGoogleLink,
)
from studymate.domain.identity import StudentEmail
from studymate.domain.membership import Membership
from studymate.domain.profiles import DisplayName
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.onboarding_models import (
    ProfileActivationRecord,
    VisibilityRevisionRecord,
)
from studymate.infrastructure.persistence.profile_models import ProfileRecord, ProfileRevisionRecord
from studymate.infrastructure.persistence.registration_models import RegistrationReceiptRecord
from studymate.infrastructure.persistence.registration_reads import read_context


def account_sources() -> Select[
    AccountRecord,
    ExternalIdentityRecord | None,
    InstitutionalBindingRecord | None,
    ProfileRevisionRecord | None,
    VisibilityRevisionRecord | None,
]:
    return (
        select(
            AccountRecord,
            Nullable(ExternalIdentityRecord),
            Nullable(InstitutionalBindingRecord),
            Nullable(ProfileRevisionRecord),
            Nullable(VisibilityRevisionRecord),
        )
        .outerjoin(ExternalIdentityRecord, ExternalIdentityRecord.account_id == AccountRecord.id)
        .outerjoin(
            InstitutionalBindingRecord, InstitutionalBindingRecord.account_id == AccountRecord.id
        )
        .outerjoin(ProfileRecord, ProfileRecord.account_id == AccountRecord.id)
        .outerjoin(
            ProfileRevisionRecord,
            and_(
                ProfileRevisionRecord.account_id == ProfileRecord.account_id,
                ProfileRevisionRecord.version == ProfileRecord.current_version,
            ),
        )
        .outerjoin(ProfileActivationRecord, ProfileActivationRecord.account_id == AccountRecord.id)
        .outerjoin(
            VisibilityRevisionRecord,
            and_(
                VisibilityRevisionRecord.account_id == ProfileActivationRecord.account_id,
                VisibilityRevisionRecord.version == ProfileActivationRecord.visibility_version,
            ),
        )
    )


def account_summary(
    account: AccountRecord,
    google: ExternalIdentityRecord | None,
    binding: InstitutionalBindingRecord | None,
    profile: ProfileRevisionRecord | None,
    visibility: VisibilityRevisionRecord | None,
) -> OperatorAccountSummary:
    return OperatorAccountSummary(
        account.id,
        account.created_at,
        account.banned_at,
        account.deleted_at,
        StoredGoogleLink(
            google.id, google.account_id, google.issuer, google.subject, google.created_at
        )
        if google is not None
        else None,
        OperatorMembershipSnapshot(
            binding.account_id,
            Membership(StudentEmail(binding.email), binding.verified_at, binding.revoked_at),
        )
        if binding is not None
        else None,
        profile.version if profile is not None else None,
        DisplayName(profile.display_name)
        if profile is not None and profile.display_name is not None
        else None,
        visibility.hidden_at if visibility is not None else None,
    )


async def registration_snapshot(
    session: AsyncSession, account_id: UUID
) -> OperatorRegistrationSnapshot | None:
    receipt = await session.scalar(
        select(RegistrationReceiptRecord).where(RegistrationReceiptRecord.account_id == account_id)
    )
    if receipt is None:
        return None
    context = await read_context(session, receipt.context_id)
    if (
        context is None
        or context.account_id != account_id
        or context.completed_at != receipt.registered_at
    ):
        raise RuntimeError("Operator registration projection lost its actual stored completion")
    return OperatorRegistrationSnapshot(
        receipt.id,
        account_id,
        context.id,
        receipt.registered_at,
        context.terms,
        context.privacy,
        context.notice_text,
        context.surface,
    )
