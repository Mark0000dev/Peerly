"""Deterministic historical records for privileged reads, not student write acceptance.

All real foreign keys remain enabled. Fixed past source facts make IDs/timestamps
inspectable in PNGs. Live session/grant/audit clocks are not overridden. Photo
metadata is retained only; these cohorts do not promise an object-store binary.
"""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.infrastructure.persistence.help_models import (
    HelpRecord,
    HelpRevisionRecord,
    HelpSelectionRecord,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.media_models import (
    PhotoRecord,
    PhotoRevisionRecord,
    PhotoUploadRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.onboarding_models import (
    ProfileActivationRecord,
    VisibilityRevisionRecord,
)
from studymate.infrastructure.persistence.photo_attempt_models import PhotoAttemptRecord
from studymate.infrastructure.persistence.profile_models import (
    ProfileLanguageRecord,
    ProfileRecord,
    ProfileRevisionRecord,
)
from studymate.infrastructure.persistence.registration_models import (
    RegistrationContextRecord,
    RegistrationReceiptRecord,
)

SOURCE_TIME = datetime(2026, 1, 5, 4, tzinfo=UTC)


def retained_id(namespace: str, label: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"peerly-operator-fixture/{namespace}/{label}")


async def seed_retained_targets(engine: AsyncEngine, namespace: str) -> dict[str, str]:
    result: dict[str, str] = {}
    async with async_sessionmaker(engine).begin() as session:
        for index, state in enumerate(("active", "hidden", "banned", "deleted")):
            owner = retained_id(namespace, state)

            def key(label: str, *, prefix: str = state) -> UUID:
                return retained_id(namespace, prefix + "/" + label)

            at = SOURCE_TIME + timedelta(days=index)
            changed = at + timedelta(hours=1)
            session.add(
                AccountRecord(
                    id=owner,
                    created_at=at,
                    banned_at=changed if state == "banned" else None,
                    deleted_at=changed if state == "deleted" else None,
                )
            )
            await session.flush()
            session.add(
                ExternalIdentityRecord(
                    id=key("google"),
                    account_id=owner,
                    issuer=GOOGLE_ISSUER,
                    subject="synthetic-" + str(owner),
                    created_at=at,
                )
            )
            session.add(
                SessionRecord(
                    id=key("session"),
                    account_id=owner,
                    secret_digest=sha256(str(key("session")).encode()).digest(),
                    issued_at=at,
                    expires_at=at + timedelta(days=1),
                )
            )
            session.add(
                InstitutionalBindingRecord(
                    account_id=owner,
                    email=f"retained-{owner.hex}@mail.apu.edu.my",
                    verified_at=at,
                )
            )
            session.add(
                ProfileRevisionRecord(
                    account_id=owner,
                    version=1,
                    display_name="Retained " + state.title(),
                    about="Stored profile for operator inspection.",
                    programme="Computing",
                    year_label="Year 1",
                    task="offer_help",
                    saved_at=at,
                )
            )
            session.add(HelpRevisionRecord(account_id=owner, version=1, saved_at=at))
            session.add(
                PhotoUploadRecord(
                    id=key("upload"),
                    account_id=owner,
                    current_version=1,
                    expected_photo_version=0,
                    source_size=64,
                    source_digest=bytes.fromhex("03" * 32),
                    content_type="image/png",
                    created_at=at,
                    upload_expires_at=at + timedelta(minutes=10),
                    processing_expires_at=at + timedelta(hours=1),
                )
            )
            await session.flush()
            session.add(ProfileRecord(account_id=owner, current_version=1))
            session.add(
                ProfileLanguageRecord(account_id=owner, version=1, slot=0, code="en")
            )
            session.add(HelpRecord(account_id=owner, current_version=1))
            session.add(
                HelpSelectionRecord(
                    account_id=owner,
                    version=1,
                    slot=0,
                    subject_id=UUID(int=31),
                    subject_label="SQL",
                    topic_note=None,
                    topic_match_key=None,
                )
            )
            session.add(
                PhotoAttemptRecord(
                    id=key("attempt"),
                    upload_id=key("upload"),
                    number=1,
                    started_at=at,
                    lease_until=at + timedelta(minutes=1),
                    finished_at=at,
                    outcome="ready",
                    display_width=64,
                    display_height=64,
                    display_size=64,
                    display_digest=bytes.fromhex("04" * 32),
                )
            )
            session.add(
                RegistrationContextRecord(
                    id=key("context"),
                    account_id=owner,
                    session_id=key("session"),
                    terms_id=UUID(int=10),
                    privacy_id=UUID(int=11),
                    notice_text="Controlled retained registration notice.",
                    surface="onboarding_completion",
                    intent_key=str(key("context-intent")),
                    created_at=at,
                    expires_at=at + timedelta(minutes=10),
                    completed_at=at,
                )
            )
            await session.flush()
            session.add(
                PhotoUploadRevisionRecord(
                    upload_id=key("upload"),
                    version=1,
                    account_id=owner,
                    state="ready",
                    updated_at=at,
                    attempt_id=key("attempt"),
                )
            )
            session.add(
                RegistrationReceiptRecord(
                    id=key("receipt"),
                    account_id=owner,
                    context_id=key("context"),
                    registered_at=at,
                    intent_key=str(key("receipt-intent")),
                )
            )
            await session.flush()
            session.add(
                PhotoRevisionRecord(
                    account_id=owner,
                    version=1,
                    upload_id=key("upload"),
                    upload_version=1,
                    upload_state="ready",
                    saved_at=at,
                )
            )
            await session.flush()
            session.add(PhotoRecord(account_id=owner, current_version=1))
            session.add(
                ProfileActivationRecord(
                    account_id=owner,
                    registration_id=key("receipt"),
                    profile_version=1,
                    photo_version=1,
                    goal_id=None,
                    goal_version=None,
                    help_version=1,
                    completed_at=at,
                    visibility_version=1,
                )
            )
            await session.flush()
            session.add(
                VisibilityRevisionRecord(
                    account_id=owner,
                    version=1,
                    completed_at=at,
                    hidden_at=changed if state == "hidden" else None,
                    changed_at=changed,
                )
            )
            result[state + "_id"] = str(owner)
    return result
