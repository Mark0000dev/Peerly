"""Parent-provisioned proof receipt plus live deployment fingerprints; never a public flag."""

import asyncio
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from studymate.infrastructure.ai.runtime.policy import InspectionPolicy
from studymate.infrastructure.ai.runtime.preflight import PinnedCli

MAX_RECEIPT_BYTES = 16384

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
REQUIRED_PROOFS = frozenset(
    {"tool_auth_denial", "namespace_denial", "native_resource_fit", "transport_egress"}
)


class RuntimeAcceptanceError(Exception):
    """Missing/stale/mismatched operator proof; no path or private contents in message."""


class RuntimeReceiptPendingError(RuntimeAcceptanceError):
    """Absent or validated containment receipt; parent may install provider proof."""


class RuntimeReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    schema_version: Literal[1]
    stage: Literal["containment", "provider_accepted"]
    model: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    account_binding_sha256: Digest | None = None
    prompt_version: str | None = None
    result_schema_version: str | None = None
    adapter_version: str | None = None
    deployment_id: UUID
    issued_at: datetime
    expires_at: datetime
    binary_sha256: Digest
    policy_sha256: Digest
    boot_id: UUID
    network_namespace: Annotated[str, Field(pattern=r"^net:\[[0-9]+\]$")]
    pid_namespace: Annotated[str, Field(pattern=r"^pid:\[[0-9]+\]$")]
    cgroup_membership: Annotated[str, Field(min_length=1, max_length=2048)]
    memory_max: Annotated[int, Field(gt=0, le=2147483648)]
    pids_max: Annotated[int, Field(gt=0, le=32)]
    cpu_max: Annotated[str, Field(pattern=r"^[0-9]+ [0-9]+$")]
    workspace_bytes: Annotated[int, Field(gt=0, le=67108864)]
    evidence: dict[str, Digest] = Field(min_length=4, max_length=7)


def policy_digest(cli: PinnedCli) -> str:
    # Normalize dynamic job paths; the actual adapter binds auth to CODEX_HOME.
    settings = InspectionPolicy(Path("/job"), Path("/job/auth")).overrides(cli)
    return hashlib.sha256(json.dumps(settings, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ReceiptExpectation:
    stage: Literal["containment", "provider_accepted"] = "provider_accepted"
    model: str | None = None
    account_binding_sha256: str | None = None


DEFAULT_EXPECTATION = ReceiptExpectation()


async def validate_runtime_receipt(
    path: Path,
    cli: PinnedCli,
    workspaces_root: Path,
    *,
    expectation: ReceiptExpectation = DEFAULT_EXPECTATION,
) -> RuntimeReceipt:
    required_stage, model, account_binding_sha256 = (
        expectation.stage,
        expectation.model,
        expectation.account_binding_sha256,
    )

    def validate() -> RuntimeReceipt:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            raise RuntimeReceiptPendingError("runtime_proof_pending") from None
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_mode & 0o022
                or metadata.st_uid not in {0, os.geteuid()}
                or not 0 < metadata.st_size <= MAX_RECEIPT_BYTES
            ):
                raise RuntimeAcceptanceError("runtime_proof_file")
            encoded = os.read(descriptor, MAX_RECEIPT_BYTES + 1)
        finally:
            os.close(descriptor)
        receipt = RuntimeReceipt.model_validate_json(encoded)
        at = datetime.now(UTC)
        if required_stage == "provider_accepted" and (
            model is None or account_binding_sha256 is None
        ):
            raise RuntimeAcceptanceError("runtime_proof_binding_required")
        if receipt.stage == "provider_accepted":
            from studymate.domain.ai.jobs import Versions

            expected = Versions(model) if model is not None else None
            if (
                (model is not None and receipt.model != model)
                or (
                    account_binding_sha256 is not None
                    and receipt.account_binding_sha256 != account_binding_sha256
                )
                or (
                    expected is not None
                    and (
                        receipt.prompt_version,
                        receipt.result_schema_version,
                        receipt.adapter_version,
                    )
                    != (expected.prompt, expected.schema, expected.adapter)
                )
            ):
                raise RuntimeAcceptanceError("runtime_proof_binding_changed")
        if (
            receipt.issued_at.tzinfo is None
            or receipt.expires_at.tzinfo is None
            or not receipt.issued_at <= at < receipt.expires_at
            or receipt.expires_at - receipt.issued_at > timedelta(days=1)
            or receipt.binary_sha256 != cli.sha256
            or receipt.policy_sha256 != policy_digest(cli)
            or (receipt.stage == "provider_accepted" and receipt.model != model)
            or set(receipt.evidence)
            != (
                REQUIRED_PROOFS | {"credential_refresh", "text_image_schema", "same_owner_binding"}
                if receipt.stage == "provider_accepted"
                else REQUIRED_PROOFS
            )
        ):
            raise RuntimeAcceptanceError("runtime_proof_mismatch")
        if (
            str(receipt.boot_id) != Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            or receipt.network_namespace != os.readlink("/proc/self/ns/net")
            or receipt.pid_namespace != os.readlink("/proc/self/ns/pid")
            or receipt.cgroup_membership != Path("/proc/self/cgroup").read_text().strip()
        ):
            raise RuntimeAcceptanceError("runtime_deployment_changed")
        # Dedicated cgroup namespace exposes its own root; never mount a host daemon socket.
        group = Path("/sys/fs/cgroup")
        if (
            group.joinpath("memory.max").read_text().strip() != str(receipt.memory_max)
            or group.joinpath("pids.max").read_text().strip() != str(receipt.pids_max)
            or group.joinpath("cpu.max").read_text().strip() != receipt.cpu_max
        ):
            raise RuntimeAcceptanceError("runtime_resource_limits_changed")
        status = Path("/proc/self/status").read_text()
        if (
            os.geteuid() == 0
            or "NoNewPrivs:\t1" not in status
            or "CapEff:\t0000000000000000" not in status
            or not os.statvfs("/").f_flag & os.ST_RDONLY
        ):
            raise RuntimeAcceptanceError("runtime_process_containment")
        volume = os.statvfs(workspaces_root)
        if (
            volume.f_blocks * volume.f_frsize > receipt.workspace_bytes
            or not volume.f_flag & os.ST_NOEXEC
        ):
            raise RuntimeAcceptanceError("runtime_workspace_quota")
        if required_stage == "provider_accepted" and receipt.stage == "containment":
            raise RuntimeReceiptPendingError("runtime_provider_proof_pending")
        return receipt

    try:
        return await asyncio.to_thread(validate)
    except (OSError, ValueError):
        raise RuntimeAcceptanceError("runtime_proof_invalid") from None
