from dataclasses import dataclass
from uuid import uuid4

from studymate.application.idempotency import IntentKey
from studymate.application.messaging.goal_shares import (
    ReadGoalShares,
    ShareCurrentGoal,
    ShareCurrentGoalCommand,
)
from studymate.application.profiles.goals import ReadOwnGoal
from studymate.infrastructure.messaging.goal_share_cursors import FernetGoalShareCursorCodec
from studymate.infrastructure.messaging.goal_shares import GoalShareRecorder, SqlGoalShareUnitOfWork
from studymate.infrastructure.persistence.goals import SqlGoalUnitOfWork
from studymate.infrastructure.persistence.product_events import (
    record_conversation_goal_share,
    record_message_outcome,
)
from tests.integration.requests.fixture import FINGERPRINTER, HASHER
from tests.integration.student_actor import Actor
from tests.integration.test_message_commands import Chat


@dataclass(frozen=True, slots=True)
class GoalSharing:
    unit_of_work: SqlGoalShareUnitOfWork
    share: ShareCurrentGoal
    history: ReadGoalShares


def sharing(
    context: Chat, recorder: GoalShareRecorder = record_conversation_goal_share
) -> GoalSharing:
    uow = SqlGoalShareUnitOfWork(context.api.sessions, record_message_outcome, recorder)
    return GoalSharing(
        uow,
        ShareCurrentGoal(uow, HASHER, FINGERPRINTER),
        ReadGoalShares(uow, HASHER, FernetGoalShareCursorCodec.from_key(b"x" * 32)),
    )


async def command(
    context: Chat, owner: Actor | None = None, context_version: int = 0
) -> ShareCurrentGoalCommand:
    actor = owner if owner is not None else context.sender
    goal = await ReadOwnGoal(SqlGoalUnitOfWork(context.api.sessions), HASHER)(actor.credential)
    assert goal is not None
    return ShareCurrentGoalCommand(
        actor.credential,
        context.conversation_id,
        goal.goal.id,
        goal.goal.version,
        context_version,
        IntentKey(str(uuid4())),
    )
