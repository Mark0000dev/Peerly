from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from studymate.application.ai.ports import AiSourceUnavailableError, StudentSubmission
from studymate.domain.ai.tasks import AiKind, AssessPhoto, Source
from studymate.infrastructure.ai.persistence import SqlAiUnitOfWork
from studymate.infrastructure.ai.photos import RetainedDisplayReader
from studymate.infrastructure.persistence.media_uploads import SqlMediaTransaction
from tests.integration.ai.test_queue import services
from tests.integration.media_fixture import Storage
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.student_actor import actor

pytestmark = pytest.mark.integration


async def test_reader_consumes_actual_owned_ready_photo_reference_without_extra_read_grant(
    ai_engine: AsyncEngine,
) -> None:
    owner, other = await actor(ai_engine), await actor(ai_engine)
    await ready_setup(ai_engine, owner.credential)
    api = services(ai_engine)
    async with api.sessions() as session:
        photo = await SqlMediaTransaction(session).current_photo(owner.id)
    assert photo is not None
    submission = StudentSubmission(AiKind.ASSESS_PHOTO, Source(photo.upload_id, photo.version))
    async with SqlAiUnitOfWork(api.sessions).transaction() as transaction:
        with pytest.raises(AiSourceUnavailableError):
            await transaction.prepare(other.id, submission)
        prepared = await transaction.prepare(owner.id, submission)
    assert isinstance(prepared, AssessPhoto)
    storage = Storage(b"")
    storage.retained[prepared.reference] = b"\xff\xd8\xffsynthetic-retained-display"
    assert (
        await RetainedDisplayReader(storage).display_image(prepared.reference)
        == storage.retained[prepared.reference]
    )
    # Random client IDs are not turned into storage keys or capability grants.
    async with SqlAiUnitOfWork(api.sessions).transaction() as transaction:
        with pytest.raises(AiSourceUnavailableError):
            await transaction.prepare(
                owner.id, StudentSubmission(AiKind.ASSESS_PHOTO, Source(uuid4(), 1))
            )
