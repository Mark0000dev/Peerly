import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from deployment.backup import key_recovery as keys
from deployment.backup.retention import Retention
from deployment.backup.run_backup import Plan
from deployment.backup.streaming import Expected, ReadbackError
from deployment.restore import capture_backup as capture

PRIVATE = "SYNTHETIC_PRIVATE_TRANSPORT_MATERIAL"


def plan() -> Plan:
    return Plan(
        Path("/synthetic/state"),
        "a" * 64,
        Path("/synthetic/rclone"),
        "b" * 64,
        "business-key-0001",
        "escrow-drill-0001",
        3758096384,
        Retention(14, 8, 12),
    )


def profile(
    *, version: int = 1, suffix: str = "old", endpoint: str = "https://storage.invalid"
) -> str:
    return (
        "[backup_s3]\ntype=s3\nprovider=Other\nenv_auth=false\nendpoint="
        + endpoint
        + "\naccess_key_id=synthetic-identifier\nsecret_access_key="
        + PRIVATE
        + "\n[backup_crypt]\ntype=crypt\nfilename_encryption=standard\n"
        + "directory_name_encryption=true\n"
        + "remote=backup_s3:synthetic-bucket/business-backups/crypt-v"
        + str(version)
        + "\npassword=synthetic-obscured-key-"
        + suffix
        + "\npassword2=synthetic-obscured-salt-"
        + suffix
        + "\n"
    )


@contextmanager
def descriptor(root: Path, text: str) -> Iterator[int]:
    path = root / (uuid4().hex + ".private")
    path.write_text(text)
    path.chmod(0o600)
    fd = os.open(path, os.O_RDONLY)
    try:
        yield fd
    finally:
        os.close(fd)


def test_rotation_requires_new_generation_root_and_drill_without_claiming_custody(
    tmp_path: Path,
) -> None:
    old = plan()
    new = replace(
        old, key_generation="business-key-0002", escrow_drill_reference="escrow-drill-0002"
    )
    with (
        descriptor(tmp_path, profile()) as before,
        descriptor(tmp_path, profile(version=2, suffix="new")) as after,
    ):
        result = keys.rotation(old, new, before, after)
    assert result["status"] == "rotation_mapping_validated"
    assert result["old_root_sha256"] != result["new_root_sha256"]
    assert result["independent_custody_proven"] is False
    assert result["plaintext_key_distinctness_proven"] is False
    assert result["remote_deletion_enabled"] is False


@pytest.mark.parametrize(
    "change",
    ["same-root", "same-generation", "same-drill", "same-material", "new-endpoint", "budget"],
)
def test_unversioned_or_out_of_scope_rotation_rejects(tmp_path: Path, change: str) -> None:
    old = plan()
    new = replace(
        old, key_generation="business-key-0002", escrow_drill_reference="escrow-drill-0002"
    )
    changed = profile(version=2, suffix="new")
    if change == "same-root":
        changed = profile(version=1, suffix="new")
    elif change == "same-generation":
        new = replace(new, key_generation=old.key_generation)
    elif change == "same-drill":
        new = replace(new, escrow_drill_reference=old.escrow_drill_reference)
    elif change == "same-material":
        changed = profile(version=2)
    elif change == "new-endpoint":
        changed = profile(version=2, suffix="new", endpoint="https://other.invalid")
    else:
        new = replace(new, max_spool_bytes=old.max_spool_bytes + 1)
    with (
        descriptor(tmp_path, profile()) as before,
        descriptor(tmp_path, changed) as after,
        pytest.raises(
            keys.KeyRecoveryError, match=r"unversioned|new_generation|rotation_scope"
        ) as error,
    ):
        keys.rotation(old, new, before, after)
    assert PRIVATE not in str(error.value)


@pytest.mark.parametrize(
    "tail",
    [
        "\n[source_media]\ntype=alias\nremote=media_s3:private-source\n",
        "\nno_check_certificate=true\n",
    ],
)
def test_escrow_profile_has_no_source_credentials_or_tls_bypass(tmp_path: Path, tail: str) -> None:
    text = profile()
    if "no_check_certificate" in tail:
        text = text.replace("env_auth=false", "env_auth=false\nno_check_certificate=true")
    else:
        text += tail
    with (
        descriptor(tmp_path, text) as fd,
        pytest.raises(keys.KeyRecoveryError, match=r"escrow_only|escrow_profile"),
    ):
        keys.profile(fd)


def spec(config: str) -> dict[str, object]:
    del config
    return {
        "key_generation": plan().key_generation,
        "canary_reference": "canary-0001",
        "size": 64,
        "sha256": "c" * 64,
        "crypt_root_sha256": hashlib.sha256(
            b"backup_s3:synthetic-bucket/business-backups/crypt-v1"
        ).hexdigest(),
        "endpoint_sha256": hashlib.sha256(b"https://storage.invalid").hexdigest(),
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"endpoint_sha256": "0" * 64},
        {"crypt_root_sha256": "0" * 64},
        {"size": 4097},
        {"size": True},
        {"key_generation": "other-key-0001"},
    ],
)
def test_canary_is_bound_to_generation_endpoint_root_size(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    data = spec(profile())
    data.update(changes)
    with (
        descriptor(tmp_path, profile()) as config_fd,
        descriptor(tmp_path, json.dumps(data)) as spec_fd,
        pytest.raises(keys.KeyRecoveryError, match="canary_identity_or_bounds"),
    ):
        keys.specification(spec_fd, plan(), keys.profile(config_fd))


async def test_canary_reuses_only_bounded_streaming_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    async def version(actual: Plan, fd: int, args: tuple[str, ...]) -> bytes:
        assert actual == plan()
        assert fd >= 0
        assert args == ("version",)
        return b"rclone v1.76.0\n"

    async def readback(
        actual: Plan, fd: int, remote: str, expected: dict[str, Expected], maximum: int
    ) -> dict[str, object]:
        assert actual == plan()
        assert fd >= 0
        assert remote == "backup_crypt:key-recovery/canary-0001"
        assert expected == {"KEY-RECOVERY.json": Expected(64, "c" * 64)}
        assert maximum == keys.MAX_CANARY
        calls.append("native_hash_download")
        return {"mode": "native_sha256_download", "plaintext_readback_tree_created": False}

    monkeypatch.setattr(capture, "binary_hash", lambda _path: plan().rclone_sha256)
    monkeypatch.setattr(keys, "native", version)
    monkeypatch.setattr(keys, "verify_remote", readback)
    with (
        descriptor(tmp_path, profile()) as config_fd,
        descriptor(tmp_path, json.dumps(spec(profile()))) as spec_fd,
    ):
        receipt = await keys.verify(plan(), config_fd, spec_fd)
    assert calls == ["native_hash_download"]
    assert receipt["native_key_readback_verified"] is True
    assert receipt["independent_custody_proven"] is False
    assert receipt["full_restore_proven"] is False
    assert PRIVATE not in json.dumps(receipt)


async def test_wrong_key_or_partial_native_readback_never_returns_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def version(actual: Plan, fd: int, args: tuple[str, ...]) -> bytes:
        del actual, fd, args
        return b"rclone v1.76.0\n"

    async def failed(
        actual: Plan, fd: int, remote: str, expected: dict[str, Expected], maximum: int
    ) -> dict[str, object]:
        del actual, fd, remote, expected, maximum
        raise ReadbackError("hash_command_failed")

    monkeypatch.setattr(capture, "binary_hash", lambda _path: plan().rclone_sha256)
    monkeypatch.setattr(keys, "native", version)
    monkeypatch.setattr(keys, "verify_remote", failed)
    with (
        descriptor(tmp_path, profile()) as config_fd,
        descriptor(tmp_path, json.dumps(spec(profile()))) as spec_fd,
        pytest.raises(ReadbackError, match="hash_command_failed"),
    ):
        await keys.verify(plan(), config_fd, spec_fd)


@pytest.mark.parametrize(
    "change", ["defaults", "extra-option", "empty-endpoint", "embedded-auth", "endpoint-path"]
)
def test_escrow_transport_cannot_inherit_or_override_approved_scope(
    tmp_path: Path, change: str
) -> None:
    text = profile()
    if change == "defaults":
        text = "[DEFAULT]\nsecret_access_key=unrelated-secret\n" + text
    elif change == "extra-option":
        text += "server_side_across_configs=true\n"
    else:
        endpoint = {
            "empty-endpoint": "",
            "embedded-auth": "https://user:secret@storage.invalid",
            "endpoint-path": "https://storage.invalid/unapproved",
        }[change]
        text = profile(endpoint=endpoint)
    with descriptor(tmp_path, text) as fd, pytest.raises(keys.KeyRecoveryError):
        keys.profile(fd)


async def test_cancellation_propagates_without_verified_canary_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    async def version(actual: Plan, fd: int, args: tuple[str, ...]) -> bytes:
        del actual, fd, args
        return b"rclone v1.76.0\n"

    async def cancelled(
        actual: Plan, fd: int, remote: str, expected: dict[str, Expected], maximum: int
    ) -> dict[str, object]:
        del actual, fd, remote, expected, maximum
        raise asyncio.CancelledError

    monkeypatch.setattr(capture, "binary_hash", lambda _path: plan().rclone_sha256)
    monkeypatch.setattr(keys, "native", version)
    monkeypatch.setattr(keys, "verify_remote", cancelled)
    with (
        descriptor(tmp_path, profile()) as config_fd,
        descriptor(tmp_path, json.dumps(spec(profile()))) as spec_fd,
        pytest.raises(asyncio.CancelledError),
    ):
        await keys.verify(plan(), config_fd, spec_fd)
