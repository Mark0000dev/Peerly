from datetime import timedelta

import pytest

from studymate.application.media.cleanup import CleanupPolicy


@pytest.mark.parametrize("timeout", [timedelta(), timedelta(seconds=-1), timedelta(seconds=60)])
def test_cleanup_timeout_cannot_outlive_its_claim(timeout: timedelta) -> None:
    with pytest.raises(ValueError, match="shorter than its lease"):
        CleanupPolicy(provider_timeout=timeout)
