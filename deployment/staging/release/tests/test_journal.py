from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest
from deployment.staging.release.journal import Journal

if TYPE_CHECKING:
    from pathlib import Path


def test_private_durable_single_use(tmp_path: Path) -> None:
    path = tmp_path / "attempt"
    journal = Journal(path)
    try:
        journal.checkpoint("api_map_attempt")
        assert path.read_text() == "api_map_attempt\n"
        assert stat.S_IMODE(path.stat().st_mode) == stat.S_IRUSR | stat.S_IWUSR
        with pytest.raises(FileExistsError):
            Journal(path)
        with pytest.raises(ValueError, match="invalid_phase_code"):
            journal.checkpoint("secret=value")
    finally:
        journal.close()
