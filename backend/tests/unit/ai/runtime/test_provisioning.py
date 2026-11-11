"""Provisioning validates only directory metadata, before returning any login argv."""

from pathlib import Path

import pytest

from studymate.infrastructure.ai.credentials import validate_private_runtime_directory
from studymate.infrastructure.ai.runtime.policy import INSPECTED_SHA256, INSPECTED_VERSION
from studymate.infrastructure.ai.runtime.provisioning import (
    ProvisioningConfiguration,
    prepare_ai_provisioning,
)


async def test_private_directory_validation_never_reads_existing_auth_content(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    # Deliberately not JSON: metadata validation must not open/parse this file.
    private.joinpath("auth.json").write_bytes(b"not credential data")
    await validate_private_runtime_directory(private)


async def test_symlink_at_any_component_and_nonprivate_destination_are_rejected(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    nested = private / "nested"
    nested.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(private, target_is_directory=True)
    for candidate in (alias, alias / "nested"):
        with pytest.raises(OSError, match=r"Not a directory|Too many levels"):
            await validate_private_runtime_directory(candidate)
    private.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        await validate_private_runtime_directory(private)


@pytest.mark.parametrize("nested_auth", [True, False])
async def test_provisioning_rejects_overlapping_roots_before_pin_or_login(
    tmp_path: Path, nested_auth: bool
) -> None:
    outer = tmp_path / "outer"
    inner = outer / "inner"
    auth, jobs = (inner, outer) if nested_auth else (outer, inner)
    config = ProvisioningConfiguration(
        Path("/usr/bin/missing-synthetic-codex"),
        INSPECTED_VERSION,
        INSPECTED_SHA256,
        auth,
        jobs,
        tmp_path / "receipt.json",
    )
    with pytest.raises(ValueError, match="separate"):
        await prepare_ai_provisioning(config)


async def test_provisioning_directory_must_be_owned_and_writable_private_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    private.chmod(0o500)
    with pytest.raises(ValueError, match="0700"):
        await validate_private_runtime_directory(private)
    private.chmod(0o700)
    monkeypatch.setattr(os, "geteuid", lambda: -1)
    with pytest.raises(ValueError, match="owned"):
        await validate_private_runtime_directory(private)
