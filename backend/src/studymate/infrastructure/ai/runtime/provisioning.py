"""Parent-only provision instructions, never login/token inspection during agent execution."""

from dataclasses import dataclass, field
from pathlib import Path

from studymate.infrastructure.ai.credentials import validate_private_runtime_directory
from studymate.infrastructure.ai.runtime.acceptance import (
    ReceiptExpectation,
    RuntimeAcceptanceError,
    validate_runtime_receipt,
)
from studymate.infrastructure.ai.runtime.preflight import PinnedCli


@dataclass(frozen=True, slots=True)
class ProvisioningConfiguration:
    executable: Path
    expected_version: str
    expected_sha256: str
    credential_directory: Path = field(repr=False)
    workspaces_root: Path
    acceptance_artifact: Path


@dataclass(frozen=True, slots=True)
class ProvisioningInstructions:
    command: tuple[str, ...]
    environment: tuple[tuple[str, str], ...] = field(repr=False)


async def prepare_ai_provisioning(
    configuration: ProvisioningConfiguration,
) -> ProvisioningInstructions:
    """Return instructions after proof checks; caller needs separate parent authorization."""
    for path in (
        configuration.credential_directory,
        configuration.workspaces_root,
        configuration.acceptance_artifact,
    ):
        if (
            not path.is_absolute()
            or ".." in path.parts
            or any(path.is_relative_to(root) for root in ("/home", "/root"))
        ):
            raise ValueError("Dedicated parent-provisioned paths required")
    if (
        configuration.credential_directory.is_relative_to(configuration.workspaces_root)
        or configuration.workspaces_root.is_relative_to(configuration.credential_directory)
        or configuration.acceptance_artifact.is_relative_to(configuration.credential_directory)
        or configuration.acceptance_artifact.is_relative_to(configuration.workspaces_root)
    ):
        raise ValueError("Credentials, jobs and acceptance proof must be separate")
    await validate_private_runtime_directory(configuration.credential_directory)
    await validate_private_runtime_directory(configuration.workspaces_root)
    cli = PinnedCli(
        configuration.executable, configuration.expected_version, configuration.expected_sha256
    )
    await cli.verify()
    receipt = await validate_runtime_receipt(
        configuration.acceptance_artifact,
        cli,
        configuration.workspaces_root,
        expectation=ReceiptExpectation(stage="containment"),
    )
    if receipt.stage != "containment":
        raise RuntimeAcceptanceError("provisioning_requires_containment_stage")
    return ProvisioningInstructions(
        (
            str(cli.executable),
            "-c",
            'cli_auth_credentials_store="file"',
            "-c",
            'forced_login_method="chatgpt"',
            "login",
            "--device-auth",
        ),
        (
            ("PATH", "/usr/bin:/bin"),
            ("HOME", str(configuration.workspaces_root)),
            ("CODEX_HOME", str(configuration.credential_directory)),
            ("TMPDIR", str(configuration.workspaces_root)),
            ("LANG", "C.UTF-8"),
        ),
    )
