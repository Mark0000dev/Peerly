"""Synthetic verified identities; real profile/goal/photo/registration use cases and SQL."""

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from hashlib import sha256
from io import BytesIO
from types import MappingProxyType
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from media_fixture import ControlledMedia
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.registration import (
    BeginRegistration,
    BeginRegistrationCommand,
    CompleteRegistration,
    CompleteRegistrationCommand,
)
from studymate.application.identity.sessions import SessionCredential
from studymate.application.media.uploads import (
    ChangePhotoUpload,
    PhotoUploadCommand,
    ReadOwnPhotoUpload,
    StartPhotoCommand,
    StartPhotoUpload,
    UploadAction,
)
from studymate.application.media.worker import ProcessNextPhoto
from studymate.application.profiles.basics import SaveOwnProfile, SaveProfileCommand
from studymate.application.profiles.goals import SavedGoal, SaveGoalCommand, SaveOwnGoal
from studymate.application.profiles.help_subjects import (
    SaveHelpCommand,
    SaveOwnHelpSubjects,
)
from studymate.domain.catalogue import subject_key
from studymate.domain.media import (
    MediaObjectKind,
    MediaObjectRef,
    PhotoContentType,
    PhotoSource,
    PhotoUploadState,
)
from studymate.domain.membership import GOOGLE_ISSUER
from studymate.domain.profiles import (
    DisplayName,
    LanguageCode,
    OnboardingTask,
    ProfileBasics,
)
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    GoalContent,
    HelpSubject,
    HelpSubjects,
)
from studymate.infrastructure.persistence.catalogue_models import SubjectRecord
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.help_subjects import SqlHelpUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.media_uploads import SqlMediaUnitOfWork
from studymate.infrastructure.persistence.profiles import SqlProfileUnitOfWork
from studymate.infrastructure.persistence.registration import SqlRegistrationUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher

SQL_SUBJECT_ID = UUID(int=31)
DISCOVERY_SUBJECTS = MappingProxyType(
    {
        "modes/chromium-mobile": "Relational Query Fundamentals",
        "modes/webkit-mobile": "Data Modeling",
        "modes/chromium-desktop": "Query Optimization",
        "pass/chromium-mobile": "Transaction Processing",
        "pass/webkit-mobile": "Data Integrity",
        "pass/chromium-desktop": "Relational Algebra",
        "undo/chromium-mobile": "Database Analytics",
        "undo/webkit-mobile": "Query Execution",
        "undo/chromium-desktop": "Data Storage",
    }
)


COMPOSER_SUBJECTS = MappingProxyType(
    {
        f"composer/{mode}/{case}/{project}": f"Relational queries {mode} {case} {project}"
        for mode in ("find_help", "offer_help", "study_together")
        for case in (
            "fresh",
            "outgoing",
            "incoming",
            "connected",
            "source-change",
            "lost-reply",
            "draft",
        )
        for project in ("chromium-mobile", "webkit-mobile", "chromium-desktop")
    }
)

CHAT_SUBJECTS = MappingProxyType(
    {
        f"chats/{case}/{project}": f"Chat practice {case} {project}"
        for case in (
            "empty",
            "messages",
            "goal-change",
            "deletion-messages",
            "deletion-goal-change",
            "stream",
            "image-pipeline",
            "image-recovery",
            "image-cancel",
            "image-report",
            "image-finalize-unknown",
            "image-auth-pause",
        )
        for project in ("chromium-mobile", "webkit-mobile", "chromium-desktop")
    }
)


@dataclass(frozen=True, slots=True)
class ControlledActor:
    id: UUID
    credential: SessionCredential = field(repr=False)
    name: str = field(repr=False)
    subject_id: UUID = SQL_SUBJECT_ID


async def _identity(
    engine: AsyncEngine, name: str, subject_id: UUID = SQL_SUBJECT_ID
) -> ControlledActor:
    actor = ControlledActor(
        uuid4(), SessionCredential(uuid4().hex + uuid4().hex[:11]), name, subject_id
    )
    async with async_sessionmaker(engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        if not isinstance(now, datetime):
            raise TypeError("People fixture requires the database clock")
        session.add(AccountRecord(id=actor.id, created_at=now))
        await session.flush()
        # Controlled Google-backed identity source, not a lifecycle permission
        # bypass. The real OAuth transport has its own browser integration suite.
        session.add(
            ExternalIdentityRecord(
                id=uuid4(),
                account_id=actor.id,
                issuer=GOOGLE_ISSUER,
                subject=f"controlled-person-{actor.id.hex}",
                created_at=now,
            )
        )
        session.add(
            SessionRecord(
                id=uuid4(),
                account_id=actor.id,
                secret_digest=await Sha256SessionHasher().digest(actor.credential),
                issued_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(hours=1),
            )
        )
        # Controlled membership boundary only. OAuth/OTP UI is tested in the separate photo suite.
        session.add(
            InstitutionalBindingRecord(
                account_id=actor.id,
                email=f"person-{actor.id.hex}@mail.apu.edu.my",
                verified_at=now,
            )
        )
    return actor


def _source() -> bytes:
    with Image.new("RGB", (64, 64), (180, 180, 180)) as image:
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()


async def _setup(
    engine: AsyncEngine,
    storage: ControlledMedia,
    worker: ProcessNextPhoto,
    photo_lock: asyncio.Lock,
    actor: ControlledActor,
) -> SavedGoal:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    hasher = Sha256SessionHasher()
    fingerprint = HmacIntentFingerprinter(bytes.fromhex("03" * 32))
    await SaveOwnProfile(SqlProfileUnitOfWork(sessions), hasher, fingerprint)(
        SaveProfileCommand(
            actor.credential,
            ProfileBasics(
                DisplayName(actor.name),
                about="Happy to practise SQL together.",
                programme="Computing",
                year_label="Year 1",
                languages=(LanguageCode("en"),),
            ),
            OnboardingTask.FIND_HELP,
            0,
            IntentKey(str(uuid4())),
        )
    )
    goal = await SaveOwnGoal(SqlGoalUnitOfWork(sessions), hasher, fingerprint)(
        SaveGoalCommand(
            actor.credential,
            GoalContent(
                CanonicalSubjectRef(actor.subject_id),
                topic="JOINs",
                context="Work through examples together",
            ),
            None,
            0,
            IntentKey(str(uuid4())),
        )
    )
    media = SqlMediaUnitOfWork(sessions)
    data = await asyncio.to_thread(_source)
    uploaded = await StartPhotoUpload(media, hasher, fingerprint)(
        StartPhotoCommand(
            actor.credential,
            PhotoSource(len(data), sha256(data).digest(), PhotoContentType.PNG),
            0,
            IntentKey(str(uuid4())),
        )
    )
    storage.objects[MediaObjectRef(uploaded.id, MediaObjectKind.UPLOAD)] = data
    await ChangePhotoUpload(media, hasher, fingerprint)(
        PhotoUploadCommand(
            actor.credential,
            uploaded.id,
            UploadAction.FINALIZE,
            IntentKey(str(uuid4())),
        )
    )
    read = ReadOwnPhotoUpload(media, hasher)
    async with photo_lock:
        for _ in range(10):
            current = await read(actor.credential, uploaded.id)
            if current.state == PhotoUploadState.READY:
                break
            await worker()
        else:
            raise RuntimeError("Controlled person photo did not reach READY")
    registration = SqlRegistrationUnitOfWork(sessions)
    context = await BeginRegistration(registration, hasher)(
        BeginRegistrationCommand(actor.credential, IntentKey(str(uuid4())))
    )
    await CompleteRegistration(registration, hasher)(
        CompleteRegistrationCommand(actor.credential, context.id, IntentKey(str(uuid4())))
    )
    return goal


async def seed_people(
    engine: AsyncEngine,
    storage: ControlledMedia,
    worker: ProcessNextPhoto,
    photo_lock: asyncio.Lock,
) -> dict[str, str]:
    viewer = await _identity(engine, "Maya Lee")
    peer = await _identity(engine, "Aiko Tan")
    await _setup(engine, storage, worker, photo_lock, viewer)
    await _setup(engine, storage, worker, photo_lock, peer)
    return {
        "viewer_id": str(viewer.id),
        "peer_id": str(peer.id),
        "viewer_session": viewer.credential.value,
        "peer_session": peer.credential.value,
    }


async def seed_discovery(
    engine: AsyncEngine,
    storage: ControlledMedia,
    worker: ProcessNextPhoto,
    photo_lock: asyncio.Lock,
    namespace: str,
) -> dict[str, str]:
    """A real canonical subject isolates each test cohort without changing matching."""
    labels = {**DISCOVERY_SUBJECTS, **COMPOSER_SUBJECTS, **CHAT_SUBJECTS}
    label = labels[namespace]
    subject_id = uuid5(NAMESPACE_URL, "peerly-discovery-fixture/" + namespace)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        if not isinstance(now, datetime):
            raise TypeError("Discovery fixture requires the database clock")
        if await session.get(SubjectRecord, subject_id) is not None:
            raise ValueError("Discovery fixture namespace was already seeded")
        session.add(
            SubjectRecord(
                id=subject_id,
                name=label,
                normalized_name=subject_key(label),
                created_at=now,
                archived_at=None,
            )
        )
    viewer = await _identity(engine, "Maya Lee", subject_id)
    peer = await _identity(engine, "Aiko Tan", subject_id)
    viewer_goal = await _setup(engine, storage, worker, photo_lock, viewer)
    peer_goal = await _setup(engine, storage, worker, photo_lock, peer)
    hasher = Sha256SessionHasher()
    fingerprint = HmacIntentFingerprinter(bytes.fromhex("03" * 32))
    for actor, goal in ((viewer, viewer_goal), (peer, peer_goal)):
        await SaveOwnGoal(SqlGoalUnitOfWork(sessions), hasher, fingerprint)(
            SaveGoalCommand(
                actor.credential,
                replace(goal.goal.content, shared_learning=True),
                goal.goal.id,
                goal.goal.version,
                IntentKey(str(uuid4())),
            )
        )
        await SaveOwnHelpSubjects(SqlHelpUnitOfWork(sessions), hasher, fingerprint)(
            SaveHelpCommand(
                actor.credential,
                HelpSubjects((HelpSubject(subject_id, "JOINs"),)),
                0,
                IntentKey(str(uuid4())),
            )
        )
    return {
        "viewer_id": str(viewer.id),
        "peer_id": str(peer.id),
        "viewer_session": viewer.credential.value,
        "peer_session": peer.credential.value,
        "subject_id": str(subject_id),
        "subject_label": label,
    }
