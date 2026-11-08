from dataclasses import dataclass, field
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from studymate.application.idempotency import IntentKey
from studymate.application.profiles.goals import ReadOwnGoal, SaveGoalCommand, SaveOwnGoal
from studymate.application.profiles.help_subjects import SaveHelpCommand, SaveOwnHelpSubjects
from studymate.application.requests.actions import (
    AcceptRequest,
    DeclineRequest,
    RequestAction,
    UndoDecline,
    WithdrawRequest,
)
from studymate.application.requests.ports import RequestPreview, SentRequest
from studymate.application.requests.send import PreviewRequest, SendRequest
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import RequestText
from studymate.domain.requests.states import ConnectionRequest
from studymate.domain.study_context import (
    CanonicalSubjectRef,
    GoalContent,
    HelpSubject,
    HelpSubjects,
)
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.help_subjects import SqlHelpUnitOfWork
from studymate.infrastructure.persistence.product_events import record_request_outcome
from studymate.infrastructure.requests.transactions import SqlRequestUnitOfWork
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.catalogue_fixture import subject
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.profile_lifecycle_fixture import activated, complete_existing_setup
from tests.integration.student_actor import Actor, actor

HASHER = Sha256SessionHasher()
FINGERPRINTER = HmacIntentFingerprinter(b"x" * 32)


@dataclass(slots=True)
class Recorder:
    """Actual canonical helper with explicit rollback injection; no noop fallback."""

    transitions: list[tuple[UUID, int, UUID | None]] = field(default_factory=list)
    fail: bool = False

    async def __call__(
        self, session: AsyncSession, request: ConnectionRequest, initiator_id: UUID | None
    ) -> None:
        assert session.in_transaction()
        await record_request_outcome(session, request, initiator_id)
        self.transitions.append((request.id, request.version, initiator_id))
        if self.fail:
            raise RuntimeError("Synthetic canonical boundary failure")


@dataclass(frozen=True, slots=True)
class Services:
    sessions: async_sessionmaker[AsyncSession]
    recorder: Recorder
    preview: PreviewRequest
    send: SendRequest
    decline: DeclineRequest
    undo: UndoDecline
    withdraw: WithdrawRequest
    accept: AcceptRequest


def services(engine: AsyncEngine, recorder: Recorder | None = None) -> Services:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    boundary = recorder if recorder is not None else Recorder()
    uow = SqlRequestUnitOfWork(sessions, boundary)
    return Services(
        sessions,
        boundary,
        PreviewRequest(uow, HASHER, FINGERPRINTER),
        SendRequest(uow, HASHER, FINGERPRINTER),
        DeclineRequest(uow, HASHER, FINGERPRINTER),
        UndoDecline(uow, HASHER, FINGERPRINTER),
        WithdrawRequest(uow, HASHER, FINGERPRINTER),
        AcceptRequest(uow, HASHER, FINGERPRINTER),
    )


async def prepared(engine: AsyncEngine) -> tuple[Actor, Actor, Services]:
    first = await activated(engine)
    second = await actor(engine)
    await ready_setup(engine, second.credential)
    await complete_existing_setup(engine, second)
    known = await subject(engine)
    api = services(engine)
    for student in (first, second):
        uow = SqlGoalUnitOfWork(api.sessions)
        saved = await ReadOwnGoal(uow, HASHER)(student.credential)
        assert saved is not None
        await SaveOwnGoal(uow, HASHER, FINGERPRINTER)(
            SaveGoalCommand(
                student.credential,
                GoalContent(
                    CanonicalSubjectRef(known.id), "Synthetic topic", "Private source content", True
                ),
                saved.goal.id,
                saved.goal.version,
                IntentKey(str(uuid4())),
            )
        )
        await SaveOwnHelpSubjects(SqlHelpUnitOfWork(api.sessions), HASHER, FINGERPRINTER)(
            SaveHelpCommand(
                student.credential,
                HelpSubjects((HelpSubject(known.id, "Private declared help"),)),
                0,
                IntentKey(str(uuid4())),
            )
        )
    return first, second, api


async def preview(api: Services, sender: Actor, recipient: Actor) -> RequestPreview:
    result = await api.preview(
        sender.credential, recipient.id, DiscoveryMode.FIND_HELP, IntentKey(str(uuid4()))
    )
    assert isinstance(result, RequestPreview)
    return result


async def sent(api: Services, sender: Actor, recipient: Actor) -> ConnectionRequest:
    context = await preview(api, sender, recipient)
    result = await api.send(
        sender.credential,
        recipient.id,
        context.id,
        RequestText("Explicit synthetic reviewed text", "Private separate note"),
        IntentKey(str(uuid4())),
    )
    assert isinstance(result, SentRequest)
    return result.request


def action(actor: Actor, peer: Actor, request: ConnectionRequest) -> RequestAction:
    return RequestAction(
        actor.credential, peer.id, request.id, request.version, IntentKey(str(uuid4()))
    )


async def additional_peer(engine: AsyncEngine, subject_id: UUID) -> Actor:
    peer = await actor(engine)
    await ready_setup(engine, peer.credential)
    await complete_existing_setup(engine, peer)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    goal_uow = SqlGoalUnitOfWork(sessions)
    current = await ReadOwnGoal(goal_uow, HASHER)(peer.credential)
    assert current is not None
    await SaveOwnGoal(goal_uow, HASHER, FINGERPRINTER)(
        SaveGoalCommand(
            peer.credential,
            GoalContent(CanonicalSubjectRef(subject_id), shared_learning=True),
            current.goal.id,
            current.goal.version,
            IntentKey(str(uuid4())),
        )
    )
    save = SaveOwnHelpSubjects(
        SqlHelpUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)), HASHER, FINGERPRINTER
    )
    await save(
        SaveHelpCommand(
            peer.credential, HelpSubjects((HelpSubject(subject_id),)), 0, IntentKey(str(uuid4()))
        )
    )
    return peer
