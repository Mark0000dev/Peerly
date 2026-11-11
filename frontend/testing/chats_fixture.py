"""Chat cohorts created through real membership, request and message use cases."""

import asyncio
from dataclasses import replace
from uuid import UUID, uuid4

from media_fixture import ControlledMedia
from people_fixture import CHAT_SUBJECTS, seed_discovery
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from studymate.application.idempotency import IntentKey
from studymate.application.identity.sessions import SessionCredential
from studymate.application.media.worker import ProcessNextPhoto
from studymate.application.messaging.commands import SendMessage, SendMessageCommand
from studymate.application.profiles.goals import (
    ReadOwnGoal,
    SaveGoalCommand,
    SaveOwnGoal,
)
from studymate.application.requests.actions import AcceptRequest, RequestAction
from studymate.application.requests.ports import RequestPreview, SentRequest
from studymate.application.requests.send import PreviewRequest, SendRequest
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.messaging import MessageContent
from studymate.domain.requests.context import RequestText
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.messaging import SqlMessageUnitOfWork
from studymate.infrastructure.persistence.product_events import (
    record_message_outcome,
    record_request_outcome,
)
from studymate.infrastructure.requests.transactions import SqlRequestUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher


async def seed_chats(
    engine: AsyncEngine,
    storage: ControlledMedia,
    worker: ProcessNextPhoto,
    photo_lock: asyncio.Lock,
    namespace: str,
) -> dict[str, str]:
    if namespace not in CHAT_SUBJECTS:
        raise ValueError("Unsupported controlled chat namespace")
    result = await seed_discovery(engine, storage, worker, photo_lock, namespace)
    viewer = SessionCredential(result["viewer_session"])
    peer = SessionCredential(result["peer_session"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    commands = SqlRequestUnitOfWork(sessions, record_request_outcome)
    hasher = Sha256SessionHasher()
    fingerprint = HmacIntentFingerprinter(bytes.fromhex("03" * 32))
    preview = await PreviewRequest(commands, hasher, fingerprint)(
        viewer,
        UUID(result["peer_id"]),
        DiscoveryMode.FIND_HELP,
        IntentKey(str(uuid4())),
    )
    if not isinstance(preview, RequestPreview):
        raise TypeError("Chat cohort must produce a real preview")
    sent = await SendRequest(commands, hasher, fingerprint)(
        viewer,
        UUID(result["peer_id"]),
        preview.id,
        RequestText("Could we practise this topic together?"),
        IntentKey(str(uuid4())),
    )
    if not isinstance(sent, SentRequest):
        raise TypeError("Chat cohort must persist a real request")
    accepted = await AcceptRequest(commands, hasher, fingerprint)(
        RequestAction(
            peer,
            UUID(result["viewer_id"]),
            sent.request.id,
            sent.request.version,
            IntentKey(str(uuid4())),
        )
    )
    conversation = accepted.conversation.id
    # Independent lifecycle tests must not consume the ordinary chat namespace.
    # Reuse actual setup semantics, never a previously deleted participant pair.
    case = namespace.split("/")[1].removeprefix("deletion-")
    if case == "goal-change":
        goals = SqlGoalUnitOfWork(sessions)
        previous = await ReadOwnGoal(goals, hasher)(viewer)
        if previous is None:
            raise RuntimeError("Accepted cohort requires its actual baseline goal")
        await SaveOwnGoal(goals, hasher, fingerprint)(
            SaveGoalCommand(
                viewer,
                replace(
                    previous.goal.content,
                    topic="LEFT JOIN practice",
                    context="Compare unmatched rows after our original request",
                ),
                previous.goal.id,
                previous.goal.version,
                IntentKey(str(uuid4())),
            )
        )
    if case == "messages":
        send = SendMessage(
            SqlMessageUnitOfWork(sessions, record_message_outcome), hasher, fingerprint
        )
        for author, text in (
            (viewer, "Can we practise SQL JOINs together?"),
            (peer, "Yes, let us compare INNER and LEFT JOIN examples."),
        ):
            await send(
                SendMessageCommand(
                    author,
                    conversation,
                    uuid4(),
                    MessageContent(text=text),
                    IntentKey(str(uuid4())),
                )
            )
    return {
        **result,
        "request_id": str(sent.request.id),
        "conversation_id": str(conversation),
    }


async def send_incoming_chat(
    engine: AsyncEngine, credential: SessionCredential, conversation_id: UUID
) -> dict[str, str]:
    """Only the driver-owned synthetic peer; no arbitrary user/session lookup."""
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    operation = await SendMessage(
        SqlMessageUnitOfWork(sessions, record_message_outcome),
        Sha256SessionHasher(),
        HmacIntentFingerprinter(bytes.fromhex("03" * 32)),
    )(
        SendMessageCommand(
            credential,
            conversation_id,
            uuid4(),
            MessageContent(text="Could we compare one more LEFT JOIN example?"),
            IntentKey(str(uuid4())),
        )
    )
    message = operation.message
    if message is None or message.content.text is None:
        raise RuntimeError(
            "Controlled incoming text must have a confirmed real message"
        )
    return {
        "conversation_id": str(message.conversation_id),
        "message_id": str(message.id),
        "sequence": str(message.sequence),
        "sent_at": message.sent_at.isoformat(),
        "text": message.content.text,
    }
