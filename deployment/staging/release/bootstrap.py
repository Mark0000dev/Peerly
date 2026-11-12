"""Fetch only exact main release source and locked backend tool inputs, without Git/actions."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import http.client
import json
import os
import re
import sys
from pathlib import Path

LIMIT = 16 * 1024 * 1024
FILES_LIMIT = 100
ARGUMENT_COUNT = 3
REPO = "/repos/Mark0000dev/Peerly"
RELEASE_PREFIX = "deployment/staging/release/"


async def get(path: str, token: str) -> dict[str, object]:
    def read() -> bytes:
        connection = http.client.HTTPSConnection("api.github.com", timeout=20)
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "peerly-staging-release",
                },
            )
            response = connection.getresponse()
            body = response.read(LIMIT + 1)
            if response.status != http.client.OK or len(body) > LIMIT:
                raise RuntimeError("bootstrap_response")
            return body
        finally:
            connection.close()

    raw: object = json.loads(await asyncio.to_thread(read))
    if not isinstance(raw, dict):
        raise RuntimeError("bootstrap_object")
    result: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise RuntimeError("bootstrap_key")
        result[key] = value
    return result


def mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RuntimeError("bootstrap_shape")
    return {str(key): item for key, item in value.items()}


async def fetch(sha: str, destination: Path, token: str) -> None:
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None or await asyncio.to_thread(destination.exists):
        raise RuntimeError("bootstrap_source_or_destination")
    branch = await get(REPO + "/branches/main", token)
    if mapping(branch["commit"])["sha"] != sha:
        raise RuntimeError("bootstrap_main_moved")
    tree = await get(REPO + "/git/trees/" + sha + "?recursive=1", token)
    members = tree["tree"]
    if tree.get("truncated") is not False or not isinstance(members, list):
        raise RuntimeError("bootstrap_tree")
    selected: list[dict[str, object]] = []
    for member in members:
        item = mapping(member)
        path = str(item["path"])
        if (path.startswith(RELEASE_PREFIX) and path.endswith((".py", ".toml"))) or path in {
            "backend/pyproject.toml",
            "backend/uv.lock",
            "backend/.python-version",
        }:
            if item.get("type") != "blob" or ".." in path.split("/"):
                raise RuntimeError("bootstrap_member")
            selected.append(item)
    if not 0 < len(selected) <= FILES_LIMIT:
        raise RuntimeError("bootstrap_file_count")
    await asyncio.to_thread(destination.mkdir, mode=0o700)
    for item in selected:
        blob = await get(REPO + "/git/blobs/" + str(item["sha"]), token)
        if blob.get("encoding") != "base64":
            raise RuntimeError("bootstrap_encoding")
        content = base64.b64decode(str(blob["content"]))
        git_id = hashlib.sha1(
            b"blob " + str(len(content)).encode() + b"\0" + content, usedforsecurity=False
        ).hexdigest()
        if git_id != item["sha"]:
            raise RuntimeError("bootstrap_blob")
        target = destination / str(item["path"])
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_bytes, content)


def main() -> None:
    if len(sys.argv) != ARGUMENT_COUNT:
        raise SystemExit("bootstrap_arguments")
    asyncio.run(fetch(sys.argv[1], Path(sys.argv[2]), os.environ["PEERLY_GITHUB_TOKEN"]))


if __name__ == "__main__":
    main()
