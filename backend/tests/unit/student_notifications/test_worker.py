import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from studymate.application.student_notifications.worker import DeliverNextStudentNotification
from studymate.domain.student_notifications.delivery import Claim, Delivery, Kind, Outcome


@dataclass(slots=True)
class Queue:
    item: Claim | None = field(
        default_factory=lambda: Claim(
            Delivery(uuid4(), uuid4(), Kind.MESSAGE, datetime(2027, 1, 1, tzinfo=UTC)),
            uuid4(),
            datetime(2027, 1, 1, tzinfo=UTC),
        )
    )
    eligible: bool = True
    results: list[Outcome] = field(default_factory=list)

    async def claim(self) -> Claim | None:
        return self.item

    async def authorize(self, claim: Claim) -> Delivery | None:
        return claim.delivery if self.eligible else None

    async def finish(self, _claim: Claim, outcome: Outcome) -> bool:
        self.results.append(outcome)
        return True


@dataclass(slots=True)
class Transport:
    result: Outcome = Outcome.ACCEPTED
    blocked: bool = False
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    calls: list[Delivery] = field(default_factory=list)

    async def send(self, delivery: Delivery) -> Outcome:
        self.calls.append(delivery)
        self.entered.set()
        if self.blocked:
            await asyncio.Event().wait()
        return self.result


async def test_empty_or_freshly_ineligible_never_calls_provider() -> None:
    provider = Transport()
    assert not await DeliverNextStudentNotification(Queue(item=None), provider)()
    queue = Queue(eligible=False)
    assert await DeliverNextStudentNotification(queue, provider)()
    assert provider.calls == []
    assert queue.results == []


@pytest.mark.parametrize("outcome", list(Outcome))
async def test_provider_result_persisted_without_reinterpreting_unknown(outcome: Outcome) -> None:
    queue, provider = Queue(), Transport(result=outcome)
    assert await DeliverNextStudentNotification(queue, provider)()
    assert queue.results == [outcome]
    assert len(provider.calls) == 1


async def test_transport_deadline_is_unknown_not_retry() -> None:
    queue = Queue()
    assert await DeliverNextStudentNotification(
        queue, Transport(blocked=True), timedelta(milliseconds=1)
    )()
    assert queue.results == [Outcome.UNKNOWN]


async def test_cancelled_inflight_send_marks_unknown_and_propagates() -> None:
    queue, provider = Queue(), Transport(blocked=True)
    task = asyncio.create_task(DeliverNextStudentNotification(queue, provider)())
    await asyncio.wait_for(provider.entered.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert queue.results == [Outcome.UNKNOWN]


def test_worker_boundary_rejects_unbounded_provider_deadline() -> None:
    with pytest.raises(ValueError, match="Delivery transport timeout"):
        DeliverNextStudentNotification(Queue(), Transport(), timedelta(seconds=4))
