"""Fixed Linux namespace/rlimit launch plan; no arbitrary mount or shell options.

The dedicated executor container must additionally bound aggregate CPU/memory/PIDs
and the host-backed job directory, and restrict network egress to subscription auth/model
transport. This launcher cannot attest those deployment controls.
"""

from dataclasses import dataclass
from pathlib import Path

MEBIBYTE = 1024 * 1024
FORBIDDEN_JOB_ROOTS = ("/usr", "/home", "/root", "/etc", "/proc", "/sys", "/dev", "/run")


@dataclass(frozen=True, slots=True)
class LinuxSandbox:
    bubblewrap: Path
    prlimit: Path
    address_space_bytes: int = 1024 * MEBIBYTE
    file_bytes: int = 16 * MEBIBYTE
    temporary_bytes: int = 32 * MEBIBYTE
    cpu_seconds: int = 65
    processes: int = 32
    descriptors: int = 64
    network_egress_restricted: bool = False

    def __post_init__(self) -> None:
        if any(
            not path.is_absolute() or ".." in path.parts for path in (self.bubblewrap, self.prlimit)
        ):
            raise ValueError("Sandbox executables must be absolute")
        if not self.network_egress_restricted:
            raise ValueError("Dedicated runtime egress restrictions must be configured")
        if any(
            value <= 0
            for value in (
                self.address_space_bytes,
                self.file_bytes,
                self.temporary_bytes,
                self.cpu_seconds,
                self.processes,
                self.descriptors,
            )
        ):
            raise ValueError("Positive executor resource limits are required")

    def command(self, invocation: tuple[str, ...], directory: Path) -> tuple[str, ...]:
        if (
            not invocation
            or not Path(invocation[0]).is_relative_to("/usr")
            or ".." in Path(invocation[0]).parts
        ):
            raise ValueError("Sandbox CLI must be installed inside the read-only runtime /usr")
        if (
            not directory.is_absolute()
            or directory == Path("/")
            or ".." in directory.parts
            or any(directory.is_relative_to(root) for root in FORBIDDEN_JOB_ROOTS)
        ):
            raise ValueError("A dedicated disposable job directory is required")
        # Empty mount root: no application source, developer home, sockets or secrets mounted.
        return (
            str(self.prlimit),
            f"--as={self.address_space_bytes}",
            f"--cpu={self.cpu_seconds}",
            f"--fsize={self.file_bytes}",
            f"--nproc={self.processes}",
            f"--nofile={self.descriptors}",
            "--core=0",
            "--",
            str(self.bubblewrap),
            "--unshare-all",
            "--share-net",
            "--die-with-parent",
            "--cap-drop",
            "ALL",
            "--ro-bind",
            "/usr",
            "/usr",
            "--symlink",
            "usr/bin",
            "/bin",
            "--symlink",
            "usr/lib",
            "/lib",
            "--symlink",
            "usr/lib64",
            "/lib64",
            "--ro-bind",
            "/etc/ssl/certs",
            "/etc/ssl/certs",
            "--ro-bind",
            "/etc/resolv.conf",
            "/etc/resolv.conf",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--size",
            str(self.temporary_bytes),
            "--tmpfs",
            "/scratch",
            "--bind",
            str(directory),
            str(directory),
            "--chdir",
            str(directory),
            "--",
            *invocation,
        )
