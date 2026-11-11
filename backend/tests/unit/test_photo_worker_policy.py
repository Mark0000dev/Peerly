from datetime import timedelta

import pytest

from studymate.application.media.worker import PhotoWorkerPolicy


@pytest.mark.parametrize("timeout", [timedelta(), timedelta(seconds=-1), timedelta(seconds=120)])
def test_processing_timeout_must_fit_lease(timeout: timedelta) -> None:
    with pytest.raises(ValueError, match="shorter than its lease"):
        PhotoWorkerPolicy(processing_timeout=timeout)


@pytest.mark.parametrize(
    "delays", [(), (timedelta(seconds=1),), (timedelta(), timedelta(seconds=1))]
)
def test_photo_retry_schedule_is_positive_and_bounded(delays: tuple[timedelta, ...]) -> None:
    with pytest.raises(ValueError, match="positive and bounded"):
        PhotoWorkerPolicy(retry_delays=delays)
