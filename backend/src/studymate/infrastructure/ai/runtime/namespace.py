"""Offline proof namespace. This does not route the CLI's model tools into this boundary."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class OfflineNamespace:
    bubblewrap: Path = Path("/usr/bin/bwrap")

    def command(self, job: Path, invocation: tuple[str, ...]) -> tuple[str, ...]:
        if (
            not job.is_absolute()
            or ".." in job.parts
            or job == Path("/")
            or any(job.is_relative_to(path) for path in ("/home", "/root", "/usr", "/proc", "/sys"))
        ):
            raise ValueError("Explicit non-home disposable proof directory required")
        if (
            not self.bubblewrap.is_absolute()
            or not invocation
            or not invocation[0].startswith("/usr/")
        ):
            raise ValueError("Explicit runtime executables required")
        return (
            str(self.bubblewrap),
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
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
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--size",
            "33554432",
            "--tmpfs",
            "/scratch",
            "--symlink",
            "scratch",
            "/tmp",  # noqa: S108 - alias to bounded private scratch, never a host mount.
            "--bind",
            str(job),
            "/job",
            "--chdir",
            "/job",
            "--clearenv",
            "--setenv",
            "PATH",
            "/usr/bin:/bin",
            "--setenv",
            "HOME",
            "/job",
            "--setenv",
            "CODEX_HOME",
            "/job/empty-auth",
            "--setenv",
            "TMPDIR",
            "/scratch",
            "--setenv",
            "LANG",
            "C.UTF-8",
            "--",
            *invocation,
        )
