"""Actor-owned pending requests through real setup, preview, send and event persistence."""

import asyncio
from uuid import UUID, uuid4

from media_fixture import ControlledMedia
from people_fixture import SQL_SUBJECT_ID, seed_people
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import SessionCredential
from studymate.application.media.worker import ProcessNextPhoto
from studymate.application.profiles.help_subjects import SaveHelpCommand, SaveOwnHelpSubjects
from studymate.application.requests.ports import RequestPreview, SentRequest
from studymate.application.requests.send import PreviewRequest, SendRequest
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import RequestText
from studymate.domain.study_context import HelpSubject, HelpSubjects
from studymate.infrastructure.persistence.help_subjects import SqlHelpUnitOfWork
from studymate.infrastructure.persistence.product_events import record_request_outcome
from studymate.infrastructure.requests.transactions import SqlRequestUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher


async def seed_requests(
    engine: AsyncEngine,
    storage: ControlledMedia,
    worker: ProcessNextPhoto,
    photo_lock: asyncio.Lock,
    direction: str,
) -> dict[str, str]:
    if direction not in {"received", "sent"}:
        raise ValueError("Unsupported controlled request direction")
    result = await seed_people(engine, storage, worker, photo_lock)
    viewer = SessionCredential(result["viewer_session"])
    peer = SessionCredential(result["peer_session"])
    sender, recipient, recipient_id = (
        (peer, viewer, UUID(result["viewer_id"]))
        if direction == "received"
        else (viewer, peer, UUID(result["peer_id"]))
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    hasher = Sha256SessionHasher()
    fingerprint = HmacIntentFingerprinter(bytes.fromhex("03" * 32))
    await SaveOwnHelpSubjects(SqlHelpUnitOfWork(sessions), hasher, fingerprint)(
        SaveHelpCommand(
            recipient,
            HelpSubjects((HelpSubject(SQL_SUBJECT_ID, "JOINs"),)),
            0,
            IntentKey(str(uuid4())),
        )
    )
    commands = SqlRequestUnitOfWork(sessions, record_request_outcome)
    preview = await PreviewRequest(commands, hasher, fingerprint)(
        sender, recipient_id, DiscoveryMode.FIND_HELP, IntentKey(str(uuid4()))
    )
    if not isinstance(preview, RequestPreview):
        raise TypeError("New controlled pair must produce an actual request preview")
    text = "Could we work through SQL joins together?"
    sent = await SendRequest(commands, hasher, fingerprint)(
        sender, recipient_id, preview.id, RequestText(text), IntentKey(str(uuid4()))
    )
    if not isinstance(sent, SentRequest):
        raise TypeError("New controlled pair must persist an actual pending request")
    return {**result, "request_id": str(sent.request.id), "text": text}
