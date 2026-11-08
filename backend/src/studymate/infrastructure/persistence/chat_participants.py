"""Minimal current identity sources; no Discovery policy or profile disclosure grant."""

from uuid import UUID

from sqlalchemy import Nullable, select
from sqlalchemy.ext.asyncio import AsyncSession

from studymate.application.messaging.participants import ChatParticipantSource
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.domain.profiles import DisplayName
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.media_models import (
    PhotoRecord,
    PhotoRevisionRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.profile_models import ProfileRecord, ProfileRevisionRecord

MAX_CHAT_PARTICIPANT_BATCH = 22


async def read_chat_participants(
    session: AsyncSession, account_ids: tuple[UUID, ...]
) -> dict[UUID, ChatParticipantSource]:
    if len(account_ids) > MAX_CHAT_PARTICIPANT_BATCH:
        raise ValueError("Chat participant source query exceeds its bounded scope")
    if not account_ids:
        return {}
    rows = await session.execute(
        select(
            AccountRecord.id,
            ProfileRevisionRecord.display_name,
            Nullable(PhotoRevisionRecord.version),
            Nullable(PhotoUploadRevisionRecord.upload_id),
            PhotoUploadRevisionRecord.attempt_id,
        )
        .select_from(AccountRecord)
        .outerjoin(ProfileRecord, ProfileRecord.account_id == AccountRecord.id)
        .outerjoin(
            ProfileRevisionRecord,
            (ProfileRevisionRecord.account_id == AccountRecord.id)
            & (ProfileRevisionRecord.version == ProfileRecord.current_version),
        )
        .outerjoin(PhotoRecord, PhotoRecord.account_id == AccountRecord.id)
        .outerjoin(
            PhotoRevisionRecord,
            (PhotoRevisionRecord.account_id == AccountRecord.id)
            & (PhotoRevisionRecord.version == PhotoRecord.current_version),
        )
        .outerjoin(
            PhotoUploadRevisionRecord,
            (PhotoUploadRevisionRecord.account_id == AccountRecord.id)
            & (PhotoUploadRevisionRecord.upload_id == PhotoRevisionRecord.upload_id)
            & (PhotoUploadRevisionRecord.version == PhotoRevisionRecord.upload_version)
            & (PhotoUploadRevisionRecord.state == "ready"),
        )
        .where(AccountRecord.id.in_(account_ids))
    )
    return {
        account_id: ChatParticipantSource(
            account_id,
            DisplayName(name) if name is not None else None,
            version if upload_id is not None and attempt_id is not None else None,
            MediaObjectRef(upload_id, MediaObjectKind.DISPLAY, attempt_id)
            if version is not None and upload_id is not None and attempt_id is not None
            else None,
        )
        for account_id, name, version, upload_id, attempt_id in rows
    }
