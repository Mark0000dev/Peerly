"""Read-only startup guard for the parent-provisioned bounded Tempo filesystem.

This does not create mounts, set quotas, delete WAL files or contact object storage.
The whole filesystem must fit the supplied budget: per-directory project quotas
cannot be inferred from statvfs and are deliberately not assumed.
"""

import argparse
import os
import sys


def require_budget(total: int, available: int, cap: int, minimum_free: int) -> None:
    if total <= 0 or cap <= 0 or minimum_free <= 0:
        raise ValueError("Filesystem size, cap and minimum headroom must be positive")
    if available < 0 or available > total:
        raise ValueError("Invalid available filesystem capacity")
    if total > cap:
        raise ValueError("Tempo filesystem exceeds the explicit local storage budget")
    if available < minimum_free or available * 100 < total * 15:
        raise ValueError("Tempo filesystem has insufficient startup headroom")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default="/var/tempo")
    parser.add_argument("--cap-bytes", type=int, required=True)
    parser.add_argument("--minimum-free-bytes", type=int, required=True)
    args = parser.parse_args()
    info = os.statvfs(args.path)
    require_budget(
        info.f_blocks * info.f_frsize,
        info.f_bavail * info.f_frsize,
        args.cap_bytes,
        args.minimum_free_bytes,
    )
    sys.stdout.write("Tempo bounded filesystem and startup headroom checks passed\n")


if __name__ == "__main__":
    main()
