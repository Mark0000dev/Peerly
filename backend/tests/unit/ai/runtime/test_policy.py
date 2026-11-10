from dataclasses import replace
from pathlib import Path

import pytest

from studymate.infrastructure.ai.runtime.policy import (
    INSPECTED_SHA256,
    INSPECTED_VERSION,
    InspectionPolicy,
)
from studymate.infrastructure.ai.runtime.preflight import PinnedCli


def pin() -> PinnedCli:
    return PinnedCli(Path("/usr/bin/synthetic-native"), INSPECTED_VERSION, INSPECTED_SHA256)


@pytest.mark.parametrize(
    ("job", "auth"),
    [
        ("relative", "relative/auth"),
        ("/", "/auth"),
        ("/home/job", "/home/job/auth"),
        ("/job", "/job"),
        ("/job", "/outside/auth"),
        ("/job/../outside", "/job/../outside/auth"),
    ],
)
def test_policy_rejects_ambient_or_uncontained_paths(job: str, auth: str) -> None:
    with pytest.raises(ValueError, match="private child"):
        InspectionPolicy(Path(job), Path(auth))


@pytest.mark.parametrize("field", ["version", "sha256"])
def test_policy_does_not_claim_compatibility_with_other_native_identity(field: str) -> None:
    cli = pin()
    changed = (
        replace(cli, version="codex-cli 0.168.0")
        if field == "version"
        else replace(cli, sha256="a" * 64)
    )
    with pytest.raises(ValueError, match="not reviewed"):
        InspectionPolicy(Path("/job"), Path("/job/private-auth")).overrides(changed)


def test_candidate_keeps_auth_unreadable_to_tools_and_excludes_legacy_sandbox() -> None:
    overrides = InspectionPolicy(Path("/job"), Path("/job/private-auth")).overrides(pin())
    assert "--sandbox" not in overrides
    assert 'default_permissions="peerly"' in overrides
    assert (
        'permissions.peerly.filesystem={":minimal"="read","/job"="read","/job/private-auth"="deny","/home"="deny","/root"="deny"}'
        in overrides
    )
    assert "permissions.peerly.network.enabled=false" in overrides
    assert "features.code_mode_host={enabled=false,disable_in_process_fallback=false}" in overrides
    assert "cloud.skills.enabled=false" in overrides
    assert "features.executor_capability_discovery_v2=false" in overrides
    assert "features.token_budget=false" in overrides
    assert "tools.experimental_request_user_input.enabled=false" in overrides
    assert "agents.enabled=false" in overrides
    assert 'forced_login_method="chatgpt"' in overrides
    assert all(name not in " ".join(overrides) for name in ("API_KEY", "API_TOKEN", "dangerously"))


def test_project_instructions_are_disabled_by_an_integer_zero_config_override() -> None:
    import tomllib

    arguments = InspectionPolicy(Path("/job"), Path("/job/private-auth")).overrides(pin())
    settings = arguments[1::2]
    config = tomllib.loads("\n".join(settings))
    assert type(config["project_doc_max_bytes"]) is int
    assert config["project_doc_max_bytes"] == 0
    assert [setting for setting in settings if setting.startswith("project_doc_max_bytes=")] == [
        "project_doc_max_bytes=0"
    ]
