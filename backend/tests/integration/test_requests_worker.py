import asyncio
from datetime import datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import DateTime, cast, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from studymate import bootstrap
from studymate.config import RequestsWorkerSettings
from studymate.domain.requests.states import ConnectionRequest, RequestState
from studymate.infrastructure.observability.requests import ObservedRequestExpiry
from studymate.infrastructure.persistence.discovery_freshness_models import DiscoveryExposureRecord
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.requests.reads import read_request
from tests.integration.requests.fixture import action, prepared, sent

pytestmark = pytest.mark.integration


async def test_real_expiry_worker_uses_one_connection_and_does_not_warm_users(
    identity_engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sender, recipient, api = await prepared(identity_engine)
    request = await sent(api, sender, recipient)
    declined = await api.decline(action(recipient, sender, request))
    assert declined.decline_until is not None
    async with api.sessions() as session:
        now = await session.scalar(select(cast(func.clock_timestamp(), DateTime(timezone=True))))
        schema = await session.scalar(select(func.current_schema()))
        activity = {
            record.account_id: record.last_activity_at
            for record in await session.scalars(select(DiscoveryExposureRecord))
        }
    assert isinstance(schema, str)
    assert isinstance(now, datetime)
    await asyncio.sleep(max(0.0, (declined.decline_until - now).total_seconds()) + 0.01)
    stop = asyncio.Event()
    engines: list[AsyncEngine] = []

    def engine_factory(url: str, **options: object) -> AsyncEngine:
        assert options == {
            "pool_pre_ping": True,
            "pool_size": 1,
            "max_overflow": 0,
            "pool_timeout": 2,
            "connect_args": {"timeout": 5, "server_settings": {"lock_timeout": "1000"}},
        }
        value = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=1,
            max_overflow=0,
            pool_timeout=2,
            connect_args={
                "timeout": 5,
                "server_settings": {"search_path": schema, "lock_timeout": "1000"},
            },
        )
        engines.append(value)
        return value

    class StopAfterCommit(ObservedRequestExpiry):
        async def __call__(self) -> tuple[ConnectionRequest, ...]:
            result = await super().__call__()
            assert [changed.id for changed in result] == [request.id]
            # ExpireRequests has exited its SQL transaction before this result.
            stop.set()
            return result

    monkeypatch.setattr(bootstrap, "create_async_engine", engine_factory)
    monkeypatch.setattr(bootstrap, "ObservedRequestExpiry", StopAfterCommit)
    settings = RequestsWorkerSettings(
        _env_file=None,
        database_url=SecretStr(identity_engine.url.render_as_string(hide_password=False)),
        observability=None,
    )
    await asyncio.wait_for(bootstrap.run_requests_worker(settings, stop), timeout=5)
    assert len(engines) == 1
    async with api.sessions() as session:
        final = await read_request(session, request.id)
        assert final is not None
        assert final.state == RequestState.DECLINED
        assert final.changed_at == declined.decline_until
        event = await session.scalar(
            select(ProductEventRecord).where(
                ProductEventRecord.connection_request_id == final.id,
                ProductEventRecord.connection_request_version == final.version,
            )
        )
        assert event is not None
        assert event.request_initiator_id is None
        assert event.occurred_at == declined.decline_until
        current_activity = {
            record.account_id: record.last_activity_at
            for record in await session.scalars(select(DiscoveryExposureRecord))
        }
        assert current_activity == activity
