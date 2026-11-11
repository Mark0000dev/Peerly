"""Retirement preserves source rows; active uniqueness never transfers old business data."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select
from sqlalchemy.sql.selectable import CTE

from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
)


async def retire_deleted_claims(session: AsyncSession, account_id: UUID) -> None:
    # Caller holds the actual lifecycle account lock. FK binds this exact time
    # to the retained account deletion source, not a fabricated expiry/revocation.
    at = await session.scalar(
        select(AccountRecord.deleted_at).where(AccountRecord.id == account_id)
    )
    if not isinstance(at, datetime):
        raise RuntimeError("Only an actually deleted account can retire identity claims")
    await session.execute(
        update(ExternalIdentityRecord)
        .where(
            ExternalIdentityRecord.account_id == account_id,
            ExternalIdentityRecord.retired_at.is_(None),
        )
        .values(retired_at=at)
    )
    await session.execute(
        update(InstitutionalBindingRecord)
        .where(
            InstitutionalBindingRecord.account_id == account_id,
            InstitutionalBindingRecord.retired_at.is_(None),
        )
        .values(retired_at=at)
    )


def _retained_lineage(seed: Select[UUID]) -> CTE:
    """Finite known credential associations only; UNION deduplicates cycles.

    Historical verified mailbox reuse can connect a later Google identity. A
    subsequent deletion or different mailbox must not erase a known active ban.
    No contact/chat/analytic relationships participate in this authority query.
    """
    current_google, prior_google = aliased(ExternalIdentityRecord), aliased(ExternalIdentityRecord)
    google_edges = select(
        current_google.account_id.label("source"),
        prior_google.account_id.label("target"),
    ).join(
        prior_google,
        (current_google.issuer == prior_google.issuer)
        & (current_google.subject == prior_google.subject),
    )
    current_mail, prior_mail = (
        aliased(InstitutionalBindingRecord),
        aliased(InstitutionalBindingRecord),
    )
    mail_edges = select(
        current_mail.account_id.label("source"),
        prior_mail.account_id.label("target"),
    ).join(prior_mail, current_mail.email == prior_mail.email)
    edges = google_edges.union(mail_edges).cte("retained_identity_edges")
    lineage = seed.cte("retained_identity_lineage", recursive=True)
    return lineage.union(
        select(edges.c.target).join(
            lineage,
            edges.c.source == lineage.c.account_id,
        )
    )


async def identity_lineage_banned(session: AsyncSession, account_id: UUID) -> bool:
    """A later ban of retained credentials cannot be evaded by their new actor."""
    lineage = _retained_lineage(
        select(AccountRecord.id.label("account_id")).where(
            AccountRecord.id == account_id,
        )
    )
    return bool(
        await session.scalar(
            select(
                select(AccountRecord.id)
                .join(
                    lineage,
                    lineage.c.account_id == AccountRecord.id,
                )
                .where(AccountRecord.banned_at.is_not(None))
                .exists()
            )
        )
    )


async def email_lineage_banned(session: AsyncSession, email: str) -> bool:
    lineage = _retained_lineage(
        select(InstitutionalBindingRecord.account_id).where(
            InstitutionalBindingRecord.email == email,
        )
    )
    return bool(
        await session.scalar(
            select(
                select(AccountRecord.id)
                .join(
                    lineage,
                    lineage.c.account_id == AccountRecord.id,
                )
                .where(AccountRecord.banned_at.is_not(None))
                .exists()
            )
        )
    )
