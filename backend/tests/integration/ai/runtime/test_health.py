"""Actual runtime facts, never an accepting configuration flag or receipt stand-in."""

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.ai.ports import AiUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.infrastructure.ai.runtime.health import RuntimeOwnershipError, SqlRuntimeHealth
from tests.integration.ai.test_queue import VERSIONS, goal, services, submission
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def test_cold_start_live_tuple_revoke_and_no_expired_takeover(
    identity_engine: AsyncEngine,
) -> None:
    api = services(identity_engine)
    owner = await actor(identity_engine)
    source = await goal(identity_engine, owner)
    with pytest.raises(AiUnavailableError):
        await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    health = SqlRuntimeHealth(api.sessions, uuid4(), VERSIONS)
    await health.register()
    with pytest.raises(AiUnavailableError):
        await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    await health.heartbeat(ready=True)
    created = await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    assert created.versions == VERSIONS
    await health.revoke(clean=False)
    with pytest.raises(AiUnavailableError):
        await api.submit(
            owner.credential, submission(source, "Other synthetic"), IntentKey(str(uuid4()))
        )
    replacement = SqlRuntimeHealth(api.sessions, uuid4(), VERSIONS)
    with pytest.raises(RuntimeOwnershipError):
        await replacement.register()


async def test_predecessor_queue_recovery_requires_exact_worker_token_and_generation(
    identity_engine: AsyncEngine,
) -> None:
    from studymate.domain.ai.jobs import LeaseLostError

    api = services(identity_engine)
    owner = await actor(identity_engine)
    source = await goal(identity_engine, owner)
    health = SqlRuntimeHealth(api.sessions, uuid4(), VERSIONS)
    await health.register()
    await health.heartbeat(ready=True)
    await api.submit(owner.credential, submission(source), IntentKey(str(uuid4())))
    claimed = await api.queue.claim()
    assert claimed is not None
    assert claimed.token is not None
    await health.revoke(clean=False)
    with pytest.raises(LeaseLostError):
        await api.queue.recover_stopped(
            claimed.token, claimed.generation, stopped=True, expected_worker=uuid4()
        )
    assert (await api.queue.snapshot()).occupied
    await api.queue.recover_stopped(
        claimed.token, claimed.generation, stopped=True, expected_worker=health.worker_id
    )
    assert not (await api.queue.snapshot()).occupied
    with pytest.raises(LeaseLostError):
        await api.queue.recover_stopped(
            claimed.token, claimed.generation, stopped=True, expected_worker=health.worker_id
        )
    await health.revoke(clean=True)
