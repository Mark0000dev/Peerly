"""Frozen stage eligibility; later reads never revoke already-staged safe invalidations."""

from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.domain.changes import ChangeHint, ChangeResource
from studymate.infrastructure.persistence.block_models import (
    BlockRecord,
    BlockRevisionRecord,
    RelationshipRecord,
)
from studymate.infrastructure.persistence.conversation_models import ConversationRecord
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.onboarding_models import ProfileActivationRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.profile_models import ProfileRevisionRecord
from studymate.infrastructure.requests.models import ConnectionRequestRecord, RequestRevisionRecord

ACADEMIC_KINDS = frozenset({"profile.saved", "help.saved", "photo.published"})
CONTACT_KINDS = frozenset({"profile.saved", "photo.published"})


def _source_version(event: ProductEventRecord) -> int:
    version = (
        event.profile_version
        if event.kind == "profile.saved"
        else event.help_version
        if event.kind == "help.saved"
        else event.photo_version
    )
    if version is None or isinstance(version, bool) or version < 1:
        raise RuntimeError("Academic invalidation lost its actual saved source revision")
    return version


async def academic_hints(
    session: AsyncSession, events: tuple[ProductEventRecord, ...]
) -> dict[UUID, tuple[ChangeHint, ...]]:
    selected = tuple(event for event in events if event.kind in ACADEMIC_KINDS)
    owners = frozenset(event.account_id for event in selected if event.kind in CONTACT_KINDS)
    contacts: dict[UUID, set[UUID]] = {owner: set() for owner in owners}
    if owners:
        # Relationships are retained permanently. This superset can only grow;
        # publication consumes ONLY actual outbox recipients frozen at the original stage.
        rows = await session.execute(
            select(RelationshipRecord.low_id, RelationshipRecord.high_id).where(
                or_(RelationshipRecord.low_id.in_(owners), RelationshipRecord.high_id.in_(owners))
            )
        )
        for low, high in rows:
            if low in contacts:
                contacts[low].add(high)
            if high in contacts:
                contacts[high].add(low)
    hints: dict[UUID, tuple[ChangeHint, ...]] = {}
    for event in selected:
        _source_version(event)
        recipients = (
            contacts.get(event.account_id, set()) if event.kind in CONTACT_KINDS else set()
        ) | {event.account_id}
        # The recipient's OWN account aggregate includes dependent contact views.
        # This conveys neither another account's private data nor a full-profile grant.
        hints[event.id] = tuple(
            ChangeHint(event.id, recipient, ChangeResource.ACCOUNT, recipient, None)
            for recipient in sorted(recipients)
        )
    return hints


async def _name_changed(session: AsyncSession, event: ProductEventRecord) -> bool:
    version = _source_version(event)
    current = await session.get(ProfileRevisionRecord, (event.account_id, version))
    if current is None:
        raise RuntimeError("Profile invalidation lost its stored profile revision")
    previous = (
        await session.scalar(
            select(ProfileRevisionRecord.display_name).where(
                ProfileRevisionRecord.account_id == event.account_id,
                ProfileRevisionRecord.version == version - 1,
            )
        )
        if version > 1
        else None
    )
    return current.display_name != previous


async def _current_contacts(session: AsyncSession, owner: UUID) -> frozenset[UUID]:
    pair, block, block_revision = RelationshipRecord, BlockRecord, BlockRevisionRecord
    request, request_revision = ConnectionRequestRecord, RequestRevisionRecord
    now = func.clock_timestamp()
    peer = case((pair.low_id == owner, pair.high_id), else_=pair.low_id)
    accepted = (
        select(ConversationRecord.id).where(ConversationRecord.relationship_id == pair.id).exists()
    )
    pending = (
        select(request.id)
        .join(
            request_revision,
            (request_revision.request_id == request.id)
            & (request_revision.version == request.current_version),
        )
        .where(
            request.relationship_id == pair.id,
            request.state.in_(("pending", "pending_decline")),
            request.expires_at > now,
            or_(request.state != "pending_decline", request_revision.decline_until > now),
        )
        .exists()
    )
    blocked = (
        select(block.relationship_id)
        .join(
            block_revision,
            (block_revision.relationship_id == block.relationship_id)
            & (block_revision.blocker_id == block.blocker_id)
            & (block_revision.version == block.current_version),
        )
        .where(block.relationship_id == pair.id, block_revision.blocked.is_(True))
        .exists()
    )
    recipients = await session.scalars(
        select(AccountRecord.id)
        .select_from(pair)
        .join(AccountRecord, AccountRecord.id == peer)
        .join(InstitutionalBindingRecord, InstitutionalBindingRecord.account_id == AccountRecord.id)
        .join(ProfileActivationRecord, ProfileActivationRecord.account_id == AccountRecord.id)
        .where(
            or_(pair.low_id == owner, pair.high_id == owner),
            or_(accepted, pending),
            ~blocked,
            AccountRecord.banned_at.is_(None),
            AccountRecord.deleted_at.is_(None),
            InstitutionalBindingRecord.revoked_at.is_(None),
            InstitutionalBindingRecord.verified_at <= now,
        )
    )
    # Hidden/freshness pause and changed goals/photo are not accepted-chat permissions.
    return frozenset(recipients)


async def eligible_academic_hints(
    session: AsyncSession, event: ProductEventRecord, hints: tuple[ChangeHint, ...]
) -> tuple[ChangeHint, ...]:
    if event.kind not in CONTACT_KINDS or not any(
        hint.recipient_id != event.account_id for hint in hints
    ):
        return hints
    if event.kind == "profile.saved" and not await _name_changed(session, event):
        return tuple(hint for hint in hints if hint.recipient_id == event.account_id)
    allowed = await _current_contacts(session, event.account_id)
    return tuple(
        hint
        for hint in hints
        if hint.recipient_id == event.account_id or hint.recipient_id in allowed
    )
