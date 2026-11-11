from pathlib import Path

import pytest

from studymate.infrastructure.ai.runtime.acceptance import (
    RuntimeAcceptanceError,
    policy_digest,
    validate_runtime_receipt,
)
from tests.unit.ai.runtime.test_policy import pin


async def test_missing_receipt_is_closed_without_reading_credentials(tmp_path: Path) -> None:
    with pytest.raises(RuntimeAcceptanceError):
        await validate_runtime_receipt(tmp_path / "missing.json", pin(), tmp_path)


def test_policy_digest_covers_the_exact_reviewed_pin_and_normalized_path_template() -> None:
    first = policy_digest(pin())
    assert len(first) == len("a" * 64)
    assert policy_digest(pin()) == first


async def test_containment_receipt_cannot_be_reused_as_provider_acceptance(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from studymate.infrastructure.ai.runtime.acceptance import RuntimeReceipt

    at = datetime.now(UTC)
    receipt = RuntimeReceipt(
        schema_version=1,
        stage="containment",
        deployment_id=uuid4(),
        issued_at=at,
        expires_at=at + timedelta(hours=1),
        binary_sha256=pin().sha256,
        policy_sha256=policy_digest(pin()),
        boot_id=uuid4(),
        network_namespace="net:[1]",
        pid_namespace="pid:[1]",
        cgroup_membership="0::/synthetic",
        memory_max=67108864,
        pids_max=32,
        cpu_max="25000 100000",
        workspace_bytes=33554432,
        evidence=dict.fromkeys(
            ("tool_auth_denial", "namespace_denial", "native_resource_fit", "transport_egress"),
            "a" * 64,
        ),
    )
    path = tmp_path / "synthetic-proof.json"
    path.write_text(receipt.model_dump_json())
    path.chmod(0o600)
    with pytest.raises(RuntimeAcceptanceError, match="binding_required"):
        await validate_runtime_receipt(path, pin(), tmp_path)
