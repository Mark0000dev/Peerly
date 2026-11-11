from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from studymate.infrastructure.ai.sandbox import LinuxSandbox

if TYPE_CHECKING:
    from collections.abc import Callable


def sandbox() -> LinuxSandbox:
    return LinuxSandbox(
        Path("/usr/bin/bwrap"), Path("/usr/bin/prlimit"), network_egress_restricted=True
    )


@pytest.mark.parametrize(
    "operation",
    [
        lambda s: replace(s, bubblewrap=Path("relative")),
        lambda s: replace(s, prlimit=Path("relative")),
        lambda s: replace(s, prlimit=Path("/usr/../jobs/prlimit")),
        lambda s: replace(s, network_egress_restricted=False),
        lambda s: replace(s, address_space_bytes=0),
        lambda s: replace(s, file_bytes=0),
        lambda s: replace(s, temporary_bytes=0),
        lambda s: replace(s, processes=0),
    ],
)
def test_sandbox_does_not_silently_fall_back_to_unrestricted_execution(
    operation: "Callable[[LinuxSandbox], LinuxSandbox]",
) -> None:
    with pytest.raises(ValueError, match=r"absolute|egress|Positive"):
        operation(sandbox())


@pytest.mark.parametrize(
    ("command", "directory"),
    [
        ((), Path("/job")),
        (("/home/developer/codex",), Path("/job")),
        (("/usr/bin/codex",), Path("/")),
        (("/usr/bin/codex",), Path("relative")),
        (("/usr/bin/codex",), Path("/usr/job")),
        (("/usr/../jobs/tool",), Path("/jobs/synthetic")),
        (("/usr/bin/codex",), Path("/jobs/../home/developer")),
        *(
            (("/usr/bin/codex",), Path(root) / "job")
            for root in ("/home", "/root", "/etc", "/proc", "/sys", "/dev", "/run")
        ),
    ],
)
def test_arbitrary_executable_mount_root_or_shared_runtime_workspace_is_rejected(
    command: tuple[str, ...], directory: Path
) -> None:
    with pytest.raises(ValueError, match=r"runtime|disposable"):
        sandbox().command(command, directory)


def test_launcher_exposes_only_fixed_runtime_and_job_mounts_with_hard_limits() -> None:
    invocation = ("/usr/bin/codex", "exec", "--ephemeral", "-")
    command = sandbox().command(invocation, Path("/jobs/synthetic"))
    assert command[-len(invocation) :] == invocation
    assert "--unshare-all" in command
    assert "--die-with-parent" in command
    assert "--core=0" in command
    assert "--nproc=32" in command
    assert "--nofile=64" in command
    assert "--cap-drop" in command
    binds = [
        (command[index + 1], command[index + 2])
        for index, value in enumerate(command)
        if value == "--bind"
    ]
    assert binds == [("/jobs/synthetic", "/jobs/synthetic")]
    assert "/home" not in command
    assert "/run" not in command
    assert command.count("--share-net") == 1


def test_nested_cli_temporary_path_is_private_bounded_scratch() -> None:
    command = sandbox().command(("/usr/bin/codex",), Path("/jobs/synthetic"))
    aliases = [command[i + 1 : i + 3] for i, value in enumerate(command) if value == "--symlink"]
    assert ("scratch", str(Path("/") / "tmp")) in aliases
    assert (str(Path("/") / "tmp"),) * 2 not in [
        command[i + 1 : i + 3]
        for i, value in enumerate(command)
        if value in {"--bind", "--ro-bind"}
    ]
    offset = command.index("--tmpfs")
    assert command[offset - 2 : offset + 2] == (
        "--size",
        str(sandbox().temporary_bytes),
        "--tmpfs",
        "/scratch",
    )
