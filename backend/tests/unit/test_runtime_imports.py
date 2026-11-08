import asyncio
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


async def test_runtime_imports_without_development_packages_or_environment() -> None:
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(BACKEND / "tests/runtime_import_smoke.py"),
        str(BACKEND / "src"),
        env={"PATH": os.defpath},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(30):
            stdout, stderr = await child.communicate()
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()
    assert child.returncode == 0, stderr.decode("utf-8")
    assert b"development imports denied" in stdout
    assert not stderr
