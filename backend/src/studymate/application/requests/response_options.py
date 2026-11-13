"""R04 factual editable suggestions, not alternative acceptance or AI generation."""

from dataclasses import dataclass
from uuid import UUID

from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.application.requests.peers import request_peer
from studymate.application.requests.response_options_data import (
    LearningTooResponseOption,
    RequestResponseOption,
    RequestResponseOptions,
    ResponseGoalSource,
    ResponsePeerHelpSource,
    SwapResponseOption,
    WriteOwnResponseOption,
)
from studymate.application.requests.response_options_ports import (
    ResponseOptionsContext,
    ResponseOptionsUnitOfWork,
)
from studymate.domain.messaging import MessageContent
from studymate.domain.requests.projections import RequestPeerState
from studymate.domain.requests.states import RequestState, RequestUnavailableError


def checked_text(value: str) -> str:
    MessageContent(value)
    return value


def suggested_options(context: ResponseOptionsContext) -> tuple[RequestResponseOption, ...]:
    saved = context.own.setup.goal
    peer_help = context.peer.setup.help_subjects
    options: list[RequestResponseOption] = []
    if saved is not None and saved.goal.active:
        subject_id = saved.goal.content.canonical_subject_id
        if subject_id is not None:
            goal = ResponseGoalSource(
                saved.goal.id,
                saved.goal.version,
                subject_id,
                saved.subject_label,
                saved.goal.content.topic,
            )
            if subject_id == context.request.context.subject_id:
                options.append(
                    LearningTooResponseOption(
                        checked_text(
                            f"I'm learning {goal.subject_label} too. "
                            "Want to work through it together?"
                        ),
                        goal,
                    )
                )
            if peer_help is not None:
                for selection, label in zip(
                    peer_help.revision.subjects.values, peer_help.labels, strict=True
                ):
                    if selection.subject_id == subject_id:
                        help_source = ResponsePeerHelpSource(
                            peer_help.revision.account_id,
                            peer_help.revision.version,
                            subject_id,
                            label,
                        )
                        own_topic = (
                            f"{goal.subject_label} — {goal.topic}"
                            if goal.topic is not None
                            else goal.subject_label
                        )
                        text = (
                            "Would you like to work through this together? "
                            f"I'm also working on {own_topic}. You listed {label}. "
                            "We could help each other if you'd like; helping back is optional."
                        )
                        options.append(SwapResponseOption(checked_text(text), goal, help_source))
                        break
    options.append(
        WriteOwnResponseOption(
            "Thanks for reaching out. Could we talk through what you have in mind?"
        )
    )
    return tuple(options)


@dataclass(frozen=True, slots=True)
class ReadRequestResponseOptions:
    unit_of_work: ResponseOptionsUnitOfWork
    hasher: SessionHasher

    async def __call__(
        self, credential: SessionCredential, request_id: UUID
    ) -> RequestResponseOptions:
        async with self.unit_of_work.transaction() as transaction:
            actor, _ = await require_verified_student(
                transaction, await self.hasher.digest(credential)
            )
            if not actor.activation_complete:
                raise StudentActionDeniedError
            actor_id = actor.session.account_id
            context = await transaction.response_context(actor_id, request_id)
            if context is None:
                raise RequestUnavailableError
            value = context.request
            if (
                value.id != request_id
                or value.context.recipient_id != actor_id
                or context.own.setup.account_id != actor_id
                or context.peer.setup.account_id != value.context.sender_id
            ):
                raise RuntimeError(
                    "Response options sources do not belong to the actual recipient/request"
                )
            peer = request_peer(context.own, context.peer, blocked=context.blocked)
            now = await transaction.now()
            if (
                value.effective(now).state != RequestState.PENDING
                or peer.state != RequestPeerState.PUBLIC
            ):
                raise RequestUnavailableError
            options = suggested_options(context)
            result = RequestResponseOptions(
                value.id,
                value.version,
                value.context.sender_id,
                now,
                value.expires_at,
                options[0].kind,
                options,
            )
            if not actor.session.is_active(await transaction.now()):
                raise UnauthenticatedError
            return result
