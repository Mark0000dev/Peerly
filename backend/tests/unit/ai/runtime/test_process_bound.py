"""Finite opt-in process contracts preserve the deployed32 policy and provider argv."""

from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker

from studymate.application.ai.worker import ExecuteNextJob
from studymate.infrastructure.ai.process import CodexProcessExecutor
from studymate.infrastructure.ai.runtime.acceptance import (
    ReceiptExpectation,
    RuntimeReceipt,
    policy_digest,
)
from studymate.infrastructure.ai.runtime.factory import create_ai_worker_runtime
from studymate.infrastructure.ai.runtime.launch import PinnedProcessPolicy
from studymate.infrastructure.ai.runtime.policy import InspectionPolicy
from studymate.infrastructure.ai.runtime.provisioning import ProvisioningConfiguration
from tests.integration.media_fixture import Storage
from tests.unit.ai.runtime.test_factory import configuration
from tests.unit.ai.runtime.test_policy import pin
from tests.unit.ai.runtime.test_process_bound_receipts import receipt
from tests.unit.ai.test_sandbox import sandbox

DEFAULT_DIGEST = "ee0382dae2d63e2bb64b1ee778cc15388aa8d58e21670cc8eb2f099a892a1bf8"
OPT_IN_PROCESSES = 40


def test_default_digest_is_byte_exact_and_override_changes_only_resource_identity() -> None:
    default = InspectionPolicy(Path("/job"), Path("/job/auth"))
    alternate = replace(default, max_processes=40)
    assert policy_digest(pin()) == DEFAULT_DIGEST
    assert policy_digest(pin(), max_processes=32) == DEFAULT_DIGEST
    assert policy_digest(pin(), max_processes=40) != DEFAULT_DIGEST
    assert alternate.overrides(pin()) == default.overrides(pin())
    assert (
        replace(sandbox(), processes=40).command(("/usr/bin/codex",), Path("/jobs/test"))[4]
        == "--nproc=40"
    )


@pytest.mark.parametrize("value", [0, 31, 41, 2**31, True])
def test_invalid_or_unbounded_contracts_rejected_before_runtime_io(
    value: int, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="32 through40"):
        InspectionPolicy(Path("/job"), Path("/job/auth"), value)
    with pytest.raises(ValueError, match="32 through40"):
        ReceiptExpectation(max_processes=value)
    with pytest.raises(ValueError, match="32 through40"):
        policy_digest(pin(), max_processes=value)
    with pytest.raises(ValueError, match="32 through40"):
        PinnedProcessPolicy(pin(), value)
    with pytest.raises(ValueError, match="32 through40"):
        replace(configuration(tmp_path), max_processes=value)
    with pytest.raises(ValueError, match=r"Positive|32 through40"):
        replace(sandbox(), processes=value)
    with pytest.raises(ValueError, match="32 through40"):
        ProvisioningConfiguration(
            pin().executable,
            pin().version,
            pin().sha256,
            tmp_path / "auth",
            tmp_path / "jobs",
            tmp_path / "receipt.json",
            value,
        )


def test_factory_binds_child_prlimit_and_launch_policy_to_same_opt_in(tmp_path: Path) -> None:
    runtime = create_ai_worker_runtime(
        async_sessionmaker(),
        Storage(b"synthetic"),
        replace(configuration(tmp_path), max_processes=40),
    )
    assert isinstance(runtime.supervisor.step, ExecuteNextJob)
    executor = runtime.supervisor.step.executor
    assert isinstance(executor, CodexProcessExecutor)
    child = executor.configuration.sandbox
    assert child is not None
    assert child.processes == OPT_IN_PROCESSES
    assert "--nproc=40" in child.command(("/usr/bin/codex",), Path("/jobs/test"))
    assert isinstance(executor.policy, PinnedProcessPolicy)
    assert executor.policy.max_processes == OPT_IN_PROCESSES


@pytest.mark.parametrize("value", [31, 41, 0, "max"])
def test_receipt_schema_does_not_admit_outside_or_unbounded_ceiling(value: int | str) -> None:
    with pytest.raises(ValidationError, match="pids_max"):
        RuntimeReceipt.model_validate({**receipt(32).model_dump(), "pids_max": value})


@pytest.mark.parametrize("boundary", ["worker", "renew", "validation", "recovery", "provisioning"])
async def test_all_private_entrypoints_require_the_selected_bound_before_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    import asyncio
    from datetime import UTC, datetime
    from uuid import uuid4

    from studymate.domain.ai.tasks import ClarifyGoal, Source
    from studymate.infrastructure.ai.runtime import factory, provisioning, recovery
    from studymate.infrastructure.ai.runtime.acceptance import RuntimeAcceptanceError
    from studymate.infrastructure.ai.runtime.factory import create_ai_validation_runtime
    from studymate.infrastructure.ai.runtime.preflight import PinnedCli
    from studymate.infrastructure.ai.runtime.provisioning import prepare_ai_provisioning
    from studymate.infrastructure.ai.runtime.recovery import StoppedPredecessorEvidence

    async def verify(_self: PinnedCli) -> None:
        return None

    async def reject(
        *_args: object, expectation: ReceiptExpectation, **_kwargs: object
    ) -> RuntimeReceipt:
        assert expectation.max_processes == OPT_IN_PROCESSES
        raise RuntimeAcceptanceError("synthetic_bound_checked")

    for module in (factory, provisioning, recovery):
        monkeypatch.setattr(module, "validate_runtime_receipt", reject)
    monkeypatch.setattr(PinnedCli, "verify", verify)
    monkeypatch.setattr(factory, "RUNTIME_HEARTBEAT_SECONDS", 0.001)
    inputs = replace(configuration(tmp_path), max_processes=40)
    runtime = create_ai_worker_runtime(async_sessionmaker(), Storage(b"synthetic"), inputs)

    async def attempt() -> None:
        if boundary == "worker":
            await runtime.run(asyncio.Event())
        elif boundary == "renew":
            await runtime._renew(asyncio.Event())
        elif boundary == "validation":
            await create_ai_validation_runtime(Storage(b"synthetic"), inputs).execute(
                ClarifyGoal(Source(uuid4(), 1), "Synthetic"), 1
            )
        elif boundary == "recovery":
            evidence = StoppedPredecessorEvidence(
                uuid4(), uuid4(), None, 1, datetime.now(UTC), "a" * 64, "b" * 64
            )
            await recovery.recover_stopped_predecessor(runtime, evidence)
        else:
            inputs.credential_directory.mkdir(mode=0o700)
            inputs.workspaces_root.mkdir(mode=0o700)
            await prepare_ai_provisioning(
                ProvisioningConfiguration(
                    inputs.executable,
                    inputs.expected_version,
                    inputs.expected_sha256,
                    inputs.credential_directory,
                    inputs.workspaces_root,
                    inputs.acceptance_artifact,
                    max_processes=40,
                )
            )

    with pytest.raises(RuntimeAcceptanceError, match="synthetic_bound_checked"):
        await attempt()
