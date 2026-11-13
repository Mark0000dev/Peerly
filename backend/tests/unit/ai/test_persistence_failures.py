from contextlib import AbstractAsyncContextManager
from types import TracebackType

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.ai.ports import AiUnavailableError
from studymate.application.errors import StorageUnavailableError
from studymate.infrastructure.ai import admission_transaction
from studymate.infrastructure.ai.persistence import SqlAiUnitOfWork


class UnavailableTransaction(AbstractAsyncContextManager[AsyncSession]):
    async def __aenter__(self) -> AsyncSession:
        raise StorageUnavailableError("private driver detail")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def unavailable(sessions: async_sessionmaker[AsyncSession]) -> UnavailableTransaction:
    assert sessions.kw["expire_on_commit"] is False
    return UnavailableTransaction()


async def test_isolated_ai_pool_outage_is_safe_nonblocking_feature_unavailability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admission_transaction, "open_transaction", unavailable)
    uow = SqlAiUnitOfWork(async_sessionmaker(expire_on_commit=False))

    async def submit() -> None:
        async with uow.transaction():
            raise AssertionError("No admission can occur without a transaction")

    with pytest.raises(AiUnavailableError) as failed:
        await submit()
    assert "private" not in str(failed.value)


@pytest.mark.parametrize("corrupt_result", [False, True])
def test_corrupt_private_snapshot_error_never_echoes_retained_input_or_result(
    corrupt_result: bool,
) -> None:
    from studymate.infrastructure.ai.codec import TASK_CODEC
    from studymate.infrastructure.ai.models import AiJobRecord
    from studymate.infrastructure.ai.persistence import job_value
    from tests.unit.ai.test_worker import running_job

    record = AiJobRecord(
        input_json=TASK_CODEC.dump_json(running_job().task).decode()
        if corrupt_result
        else '{"text":["PRIVATE_SNAPSHOT_SENTINEL"]}',
        result_json='{"suggestion":["PRIVATE_SNAPSHOT_SENTINEL"]}' if corrupt_result else None,
    )
    with pytest.raises(RuntimeError, match="Stored AI snapshot") as corrupt:
        job_value(record)
    assert "PRIVATE_SNAPSHOT_SENTINEL" not in str(corrupt.value)
