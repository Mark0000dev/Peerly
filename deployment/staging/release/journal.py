"""Durable private single-use attempt marker. Contains phase codes only."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class Journal:
    def __init__(self, path: Path) -> None:
        # Parent provides a private directory and a unique release-attempt path.
        # Existing attempt means reconcile, never silently reuse the marker.
        self.path = path
        self.fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def checkpoint(self, phase: str) -> None:
        if re.fullmatch(r"[a-z_]{1,64}", phase) is None:
            raise ValueError("invalid_phase_code")
        data = (phase + "\n").encode("ascii")
        written = os.write(self.fd, data)
        if written != len(data):
            raise RuntimeError("journal_short_write")
        os.fsync(self.fd)

    def close(self) -> None:
        os.close(self.fd)
