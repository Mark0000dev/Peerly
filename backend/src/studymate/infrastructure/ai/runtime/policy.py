"""Version-specific candidate for offline inspection, NOT an executor enablement grant."""

import json
from dataclasses import dataclass
from pathlib import Path

from studymate.infrastructure.ai.runtime.preflight import PinnedCli

INSPECTED_VERSION = "codex-cli 0.167.0"
INSPECTED_SHA256 = "cdcb45aaa01d0f14e298985e09465aebccd47f64ecd298aea44814af7b62bbda"
DISABLED_FEATURES = (
    "shell_tool",
    "shell_snapshot",
    "code_mode",
    "apps",
    "plugins",
    "remote_plugin",
    "plugin_discovery_prefetch",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "computer_use",
    "image_generation",
    "in_app_browser",
    "multi_agent",
    "multi_agent_v2",
    "hooks",
    "memories",
    "goals",
    "view_image",
    "skill_search",
    "skill_mcp_dependency_install",
    "workspace_dependencies",
    "token_budget",
    "guardian_approval",
    "guardianv2",
    "guardianv3",
    "agent_message_board",
    "multi_env_copy_file",
    "executor_capability_discovery",
    "executor_capability_discovery_v2",
    "sleep_tool",
    "tool_suggest",
    "request_permissions_tool",
    "send_message_to_user_async",
)


@dataclass(frozen=True, slots=True)
class InspectionPolicy:
    job: Path
    auth: Path

    def __post_init__(self) -> None:
        if (
            not self.job.is_absolute()
            or self.job == Path("/")
            or any(
                self.job.is_relative_to(root)
                for root in ("/home", "/root", "/usr", "/proc", "/sys")
            )
            or not self.auth.is_relative_to(self.job)
            or self.auth == self.job
            or any(".." in path.parts for path in (self.job, self.auth))
        ):
            raise ValueError("Dedicated namespace job and private child auth paths required")

    def overrides(self, cli: PinnedCli) -> tuple[str, ...]:
        if cli.version != INSPECTED_VERSION or cli.sha256 != INSPECTED_SHA256:
            raise ValueError("This inspection policy was not reviewed for that CLI identity")
        filesystem = (
            'permissions.peerly.filesystem={":minimal"="read",'
            + json.dumps(str(self.job))
            + '="read",'
            + json.dumps(str(self.auth))
            + '="deny","/home"="deny","/root"="deny"}'
        )
        settings = (
            *("features." + name + "=false" for name in DISABLED_FEATURES),
            # True here would construct a process provider despite host enabled=false.
            "features.code_mode_host={enabled=false,disable_in_process_fallback=false}",
            'default_permissions="peerly"',
            filesystem,
            "permissions.peerly.network.enabled=false",
            'approval_policy="never"',
            'approvals_reviewer="user"',
            'web_search="disabled"',
            "apps._default.enabled=false",
            "mcp_servers={}",
            "agents.enabled=false",
            "cloud.skills.enabled=false",
            "skills.include_instructions=false",
            "project_doc_max_bytes=0",
            "tools.experimental_request_user_input.enabled=false",
            "tools.update_plan.enabled=false",
            'cli_auth_credentials_store="file"',
            'forced_login_method="chatgpt"',
            "analytics.enabled=false",
        )
        return tuple(argument for setting in settings for argument in ("-c", setting))
