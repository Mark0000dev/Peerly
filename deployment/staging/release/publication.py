"""Emit the missing backend CI receipt from an exact local published image.

Run only after the existing Backend quality/build/smoke/push jobs. This does not
replace registry byte verification in provenance.py or any quality gate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from deployment.staging.release.data import Object, obj, require, rows, text
from deployment.staging.release.native import owned_command
from deployment.staging.release.release import SOURCE

INSPECT_SECONDS = 20


def receipt(sha: str, inspected: list[Object]) -> dict[str, str]:
    import re

    require(re.fullmatch(r"[0-9a-f]{40}", sha) is not None, "source_sha")
    require(len(inspected) == 1, "publication_inspect_count")
    row = inspected[0]
    prefix = "ghcr.io/mark0000dev/peerly-backend@"
    matches = [text(ref) for ref in rows(row.get("RepoDigests")) if text(ref).startswith(prefix)]
    require(
        len(matches) == 1
        and re.fullmatch(r"sha256:[0-9a-f]{64}", matches[0][len(prefix) :]) is not None,
        "publication_digest",
    )
    config = text(row.get("Id"))
    labels = obj(obj(row.get("Config")).get("Labels"))
    require(
        re.fullmatch(r"sha256:[0-9a-f]{64}", config) is not None
        and labels.get("org.opencontainers.image.source") == SOURCE
        and labels.get("org.opencontainers.image.revision") == sha,
        "publication_config",
    )
    return {
        "source_sha": sha,
        "image": matches[0],
        "digest": matches[0].split("@")[1],
        "smoked_image_id": config,
    }


async def inspect_image(image: str) -> bytes:
    docker = shutil.which("docker")
    require(docker is not None and os.path.isabs(docker), "docker_executable")
    if docker is None:
        raise RuntimeError("docker_executable")
    async with asyncio.timeout(INSPECT_SECONDS):
        result = await owned_command((docker, "image", "inspect", image))
    require(result.returncode == 0, "docker_inspect_failed")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--log-receipt", action="store_true")
    args = parser.parse_args()
    # Validate before passing user input to Docker. No credentials or shell.
    import re

    require(re.fullmatch(r"[0-9a-f]{40}", args.sha) is not None, "source_sha")
    image = "ghcr.io/mark0000dev/peerly-backend:staging-" + args.sha
    inspected = asyncio.run(inspect_image(image))
    data = receipt(args.sha, [obj(item) for item in rows(json.loads(inspected))])
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(data, indent=2) + "\n")
    if args.log_receipt:
        sys.stdout.write(
            "PEERLY_BACKEND_PUBLICATION_V1=" + json.dumps(data, separators=(",", ":")) + "\n"
        )


if __name__ == "__main__":
    main()
