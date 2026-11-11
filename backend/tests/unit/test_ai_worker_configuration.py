from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from studymate.config import AiWorkerRuntimeConfiguration


def configuration() -> AiWorkerRuntimeConfiguration:
    return AiWorkerRuntimeConfiguration(
        executable=Path("/usr/bin/peerly-codex"),
        expected_version="codex-cli 0.167.0",
        expected_sha256="a" * 64,
        model="explicit-model",
        credential_directory=Path("/var/lib/peerly-ai/credentials"),
        expected_account=SecretStr("synthetic-account-binding"),
        expected_login_owner=SecretStr("synthetic-owner-binding"),
        expected_oauth_issuer="https://synthetic-provider.invalid",
        expected_oauth_client_id="synthetic-oauth-client",
        acceptance_artifact=Path("/var/lib/peerly-ai/acceptance.json"),
        workspaces_root=Path("/var/lib/peerly-ai/jobs"),
    )


def test_worker_configuration_is_not_an_enablement_grant() -> None:
    value = configuration()
    assert value.workspaces_root != value.credential_directory
    assert "synthetic-account-binding" not in repr(value)
    assert "enabled" not in type(value).model_fields
    assert "isolation_confirmed" not in type(value).model_fields


@pytest.mark.parametrize(
    "path", ["relative", "/", "/home/runtime", "/root/cache", "/usr/jobs", "/var/../root"]
)
def test_worker_rejects_home_system_and_ambiguous_workspace_paths(path: str) -> None:
    with pytest.raises(ValidationError, match="Dedicated non-home"):
        AiWorkerRuntimeConfiguration.model_validate(
            configuration().model_dump() | {"workspaces_root": Path(path)}
        )


@pytest.mark.parametrize("path", ["codex", "/home/runtime/codex", "/usr/../jobs/codex"])
def test_worker_binary_path_cannot_escape_reviewed_runtime(path: str) -> None:
    with pytest.raises(ValidationError, match="absolute paths under /usr"):
        AiWorkerRuntimeConfiguration.model_validate(
            configuration().model_dump() | {"executable": Path(path)}
        )


@pytest.mark.parametrize("nested", ["credentials/jobs", "credentials"])
def test_worker_persistent_auth_never_lives_inside_disposable_cleanup_root(nested: str) -> None:
    with pytest.raises(ValidationError, match="disjoint roots"):
        AiWorkerRuntimeConfiguration.model_validate(
            configuration().model_dump() | {"workspaces_root": Path("/var/lib/peerly-ai") / nested}
        )
