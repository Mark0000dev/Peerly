"""Generate/check the trusted-main tool SHA256 manifest; no network or secrets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from deployment.staging.release_ssh.broker import MANIFEST, TOOL_PATHS, require


def expected(root: Path) -> dict[str, object]:
    return {
        "format": 1,
        "files": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in sorted(TOOL_PATHS)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    value = expected(args.root)
    path = args.root / MANIFEST
    if args.check:
        require(json.loads(path.read_bytes()) == value, "approved_tool_manifest_drift")
    else:
        path.write_text(json.dumps(value, indent=2) + "\n")


if __name__ == "__main__":
    main()
