"""Parent stop evidence is scoped to one fresh deployment and exact predecessor."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from studymate.infrastructure.ai.runtime.acceptance import RuntimeReceipt
from studymate.infrastructure.ai.runtime.health import RuntimeOwnershipError
from studymate.infrastructure.ai.runtime.recovery import StoppedPredecessorEvidence


def test_stop_attestation_rejects_another_deployment_stale_or_unbounded_evidence() -> None:
    at = datetime.now(UTC)
    receipt = RuntimeReceipt(
        schema_version=1,
        stage="containment",
        deployment_id=uuid4(),
        issued_at=at,
        expires_at=at + timedelta(hours=1),
        binary_sha256="a" * 64,
        policy_sha256="b" * 64,
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
            "c" * 64,
        ),
    )
    proof = StoppedPredecessorEvidence(
        receipt.deployment_id, uuid4(), uuid4(), 1, at, "d" * 64, "e" * 64
    )
    proof.validate(receipt)
    for invalid in (
        replace(proof, deployment_id=uuid4()),
        replace(proof, confirmed_at=at - timedelta(hours=1)),
        replace(proof, confirmed_at=at + timedelta(minutes=1)),
        replace(proof, generation=-1),
        replace(proof, physical_stop_sha256="unconfirmed"),
        replace(proof, cache_handoff_sha256="not evidence"),
    ):
        with pytest.raises(RuntimeOwnershipError):
            invalid.validate(receipt)
