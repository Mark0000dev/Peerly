"""Bounded storage rules without mounts, cloud calls or privileged I/O."""

import pytest
from deployment.observability.tempo.storage_budget import require_budget


def test_bounded_filesystem_with_headroom_is_allowed() -> None:
    require_budget(1000, 200, 1000, 150)


def test_shared_large_filesystem_cannot_masquerade_as_directory_quota() -> None:
    with pytest.raises(ValueError, match="exceeds"):
        require_budget(10000, 2000, 1000, 150)


def test_absolute_and_percentage_headroom_are_both_required() -> None:
    with pytest.raises(ValueError, match="headroom"):
        require_budget(1000, 149, 1000, 100)
    with pytest.raises(ValueError, match="headroom"):
        require_budget(1000, 200, 1000, 201)


def test_invalid_or_unbounded_inputs_are_rejected() -> None:
    for values in [
        (0, 0, 1000, 100),
        (1000, 500, 0, 100),
        (1000, -1, 1000, 100),
        (1000, 1001, 1000, 100),
        (1000, 500, 1000, 0),
    ]:
        with pytest.raises(ValueError, match=r"positive|capacity"):
            require_budget(*values)
