from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from studymate.domain.registration import (
    PolicyKind,
    PolicyReference,
    PolicyVersion,
    RegistrationContext,
    RegistrationReceipt,
    RegistrationSurface,
)
from studymate.infrastructure.persistence.registration_models import (
    PolicyDocumentRecord,
    RegistrationContextRecord,
    RegistrationReceiptRecord,
)


def context_from_record(
    record: RegistrationContextRecord,
    terms_version: str,
    terms_published: datetime,
    privacy_version: str,
    privacy_published: datetime,
) -> RegistrationContext:
    return RegistrationContext(
        id=record.id,
        account_id=record.account_id,
        session_id=record.session_id,
        terms=PolicyReference(
            record.terms_id, PolicyKind.TERMS, PolicyVersion(terms_version), terms_published
        ),
        privacy=PolicyReference(
            record.privacy_id, PolicyKind.PRIVACY, PolicyVersion(privacy_version), privacy_published
        ),
        notice_text=record.notice_text,
        created_at=record.created_at,
        expires_at=record.expires_at,
        completed_at=record.completed_at,
        surface=RegistrationSurface(record.surface),
    )


async def read_context(
    session: AsyncSession, context_id: UUID, *, lock: bool = False
) -> RegistrationContext | None:
    terms = aliased(PolicyDocumentRecord)
    privacy = aliased(PolicyDocumentRecord)
    statement = (
        select(
            RegistrationContextRecord,
            terms.version,
            terms.published_at,
            privacy.version,
            privacy.published_at,
        )
        .select_from(RegistrationContextRecord)
        .join(terms, terms.id == RegistrationContextRecord.terms_id)
        .join(privacy, privacy.id == RegistrationContextRecord.privacy_id)
        .where(RegistrationContextRecord.id == context_id)
    )
    if lock:
        statement = statement.with_for_update(of=RegistrationContextRecord)
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    record, terms_version, terms_published, privacy_version, privacy_published = row
    return context_from_record(
        record, terms_version, terms_published, privacy_version, privacy_published
    )


async def read_receipt(session: AsyncSession, account_id: UUID) -> RegistrationReceipt | None:
    terms = aliased(PolicyDocumentRecord)
    privacy = aliased(PolicyDocumentRecord)
    statement = (
        select(
            RegistrationReceiptRecord,
            RegistrationContextRecord,
            terms.version,
            terms.published_at,
            privacy.version,
            privacy.published_at,
        )
        .select_from(RegistrationReceiptRecord)
        .join(
            RegistrationContextRecord,
            RegistrationContextRecord.id == RegistrationReceiptRecord.context_id,
        )
        .join(terms, terms.id == RegistrationContextRecord.terms_id)
        .join(privacy, privacy.id == RegistrationContextRecord.privacy_id)
        .where(RegistrationReceiptRecord.account_id == account_id)
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        return None
    receipt, context, terms_version, terms_published, privacy_version, privacy_published = row
    return receipt_from_records(
        receipt,
        context_from_record(
            context, terms_version, terms_published, privacy_version, privacy_published
        ),
    )


def receipt_from_records(
    receipt: RegistrationReceiptRecord,
    context: RegistrationContext,
) -> RegistrationReceipt:
    """Map exact recorded notice/context/policy versions, never current policy or consent."""
    return RegistrationReceipt(
        receipt.id,
        receipt.account_id,
        context,
        receipt.registered_at,
        receipt.intent_key,
    )
