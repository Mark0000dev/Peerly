"""Isolated composer cohorts established through real setup and request use cases."""

import asyncio
from uuid import UUID, uuid4

from media_fixture import ControlledMedia
from people_fixture import COMPOSER_SUBJECTS, seed_discovery
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import SessionCredential
from studymate.application.media.worker import ProcessNextPhoto
from studymate.application.requests.actions import AcceptRequest, RequestAction
from studymate.application.requests.ports import RequestPreview, SentRequest
from studymate.application.requests.send import PreviewRequest, SendRequest
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import RequestText
from studymate.infrastructure.persistence.product_events import record_request_outcome
from studymate.infrastructure.requests.transactions import SqlRequestUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher


async def seed_composer(
    engine: AsyncEngine,
    storage: ControlledMedia,
    worker: ProcessNextPhoto,
    photo_lock: asyncio.Lock,
    namespace: str,
) -> dict[str, str]:
    if namespace not in COMPOSER_SUBJECTS:
        raise ValueError("Unsupported controlled composer namespace")
    _, mode, case, _ = namespace.split("/")
    result = await seed_discovery(engine, storage, worker, photo_lock, namespace)
    if case not in {"outgoing", "incoming", "connected"}:
        return result
    viewer = SessionCredential(result["viewer_session"])
    peer = SessionCredential(result["peer_session"])
    sender, recipient, sender_id, recipient_id = (
        (peer, viewer, UUID(result["peer_id"]), UUID(result["viewer_id"]))
        if case == "incoming"
        else (viewer, peer, UUID(result["viewer_id"]), UUID(result["peer_id"]))
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    commands = SqlRequestUnitOfWork(sessions, record_request_outcome)
    hasher = Sha256SessionHasher()
    fingerprint = HmacIntentFingerprinter(bytes.fromhex("03" * 32))
    preview = await PreviewRequest(commands, hasher, fingerprint)(
        sender, recipient_id, DiscoveryMode(mode), IntentKey(str(uuid4()))
    )
    if not isinstance(preview, RequestPreview):
        raise TypeError("Fresh composer pair must produce a real preview")
    sent = await SendRequest(commands, hasher, fingerprint)(
        sender,
        recipient_id,
        preview.id,
        RequestText("Could we practise this topic together?"),
        IntentKey(str(uuid4())),
    )
    if not isinstance(sent, SentRequest):
        raise TypeError("Composer pair must persist a real request")
    if case == "connected":
        await AcceptRequest(commands, hasher, fingerprint)(
            RequestAction(
                recipient,
                sender_id,
                sent.request.id,
                sent.request.version,
                IntentKey(str(uuid4())),
            )
        )
    return {**result, "request_id": str(sent.request.id)}
