"""Exact identifiers shared by transport and CLI validation."""

import re

from deployment.staging.release.data import require


def check_digest(value: str) -> None:
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None, "image_digest")


def check_sha(value: str) -> None:
    require(re.fullmatch(r"[0-9a-f]{40}", value) is not None, "source_sha")


def container_id(value: str) -> None:
    require(re.fullmatch(r"[0-9a-f]{64}", value) is not None, "container_id")
