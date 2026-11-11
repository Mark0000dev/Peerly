import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.discovery.photos import ReadDiscoveryPhoto
from studymate.application.discovery.profiles import DiscoveryProfileUnavailableError
from studymate.application.idempotency import IntentKey
from studymate.application.safety.blocks import ChangeBlockCommand, ChangeOwnBlock
from studymate.domain.media import MediaObjectRef
from studymate.infrastructure.persistence.blocks import SqlBlockUnitOfWork
from studymate.infrastructure.persistence.discovery_profiles import (
    SqlDiscoveryProfileTransaction,
    SqlDiscoveryProfileUnitOfWork,
)
from studymate.infrastructure.persistence.report_models import ProfileAccessRecord
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.image_fixture import encoded
from tests.integration.media_fixture import Storage
from tests.integration.profile_lifecycle_fixture import command as visibility_command
from tests.integration.profile_lifecycle_fixture import services as visibility_services
from tests.integration.safety_fixture import prepared

pytestmark = pytest.mark.integration


class DisplayStorage(Storage):
    async def read(self, reference: MediaObjectRef) -> bytes:
        self.started.set()
        if self.pause:
            await self.release.wait()
        return await super().read(reference)


async def test_peer_display_reads_exact_current_photo_without_issuing_profile_context(
    identity_engine: AsyncEngine,
) -> None:
    viewer, target, _ = await prepared(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions() as session:
        reference = await SqlDiscoveryProfileTransaction(session, target.id).display_reference(
            target.id, 1
        )
        before = await session.scalar(select(func.count()).select_from(ProfileAccessRecord))
    assert reference is not None
    storage = DisplayStorage(b"")
    data = encoded(format_name="JPEG")
    storage.retained[reference] = data
    read = ReadDiscoveryPhoto(
        SqlDiscoveryProfileUnitOfWork(sessions), Sha256SessionHasher(), storage
    )
    assert await read(viewer.credential, target.id, 1) == data
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ProfileAccessRecord)) == before
    storage.started.clear()
    with pytest.raises(DiscoveryProfileUnavailableError):
        await read(viewer.credential, target.id, 2)
    assert not storage.started.is_set()


@pytest.mark.parametrize("change", ["block", "hide"])
async def test_peer_display_rechecks_eligibility_after_slow_storage_without_holding_sql(
    identity_engine: AsyncEngine, change: str
) -> None:
    viewer, target, context = await prepared(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions() as session:
        reference = await SqlDiscoveryProfileTransaction(session, target.id).display_reference(
            target.id, 1
        )
    assert reference is not None
    storage = DisplayStorage(b"", pause=True)
    storage.retained[reference] = encoded(format_name="JPEG")
    read = ReadDiscoveryPhoto(
        SqlDiscoveryProfileUnitOfWork(sessions), Sha256SessionHasher(), storage
    )

    async def attempt() -> bytes | None:
        try:
            return await read(viewer.credential, target.id, 1)
        except DiscoveryProfileUnavailableError:
            return None

    async with asyncio.TaskGroup() as tasks:
        pending = tasks.create_task(attempt())
        await asyncio.wait_for(storage.started.wait(), timeout=3)
        if change == "block":
            block = ChangeOwnBlock(
                SqlBlockUnitOfWork(sessions),
                Sha256SessionHasher(),
                HmacIntentFingerprinter(bytes(range(32))),
            )
            await asyncio.wait_for(
                block(
                    ChangeBlockCommand(
                        viewer.credential, target.id, True, 0, IntentKey(str(uuid4())), context.id
                    )
                ),
                timeout=1,
            )
        else:
            visibility, _ = visibility_services(identity_engine)
            await asyncio.wait_for(visibility(visibility_command(target)), timeout=1)
        storage.release.set()
        assert await asyncio.wait_for(pending, timeout=3) is None
