"""Explicit local load scenarios, using the installed backend interpreter and pytest."""

import argparse
import asyncio
import json
import os
import signal
import sys
from pathlib import Path

ACTIVE = (100, 250, 500)
WORKERS = (10, 25)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active-users", choices=ACTIVE, type=int, default=100)
    parser.add_argument("--concurrency", choices=WORKERS, type=int, default=10)
    parser.add_argument("--mode", choices=("slow", "offline", "both"), default="both")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = REPOSITORY_ROOT
    output = args.output.resolve()
    if output == root or root in output.parents:
        parser.error("Write load artifacts outside the product repository")
    if not os.environ.get("TEST_DATABASE_URL"):
        parser.error("Set TEST_DATABASE_URL to an owned local disposable PostgreSQL database")
    output.mkdir(parents=True, exist_ok=False)
    modes = ("slow", "offline") if args.mode == "both" else (args.mode,)
    results: list[dict[str, object]] = []
    for mode in modes:
        receipt = output / f"{mode}.json"
        environment = {
            "TEST_DATABASE_URL": os.environ["TEST_DATABASE_URL"],
            "PEERLY_LOAD_ACTIVE": str(args.active_users),
            "PEERLY_LOAD_CONCURRENCY": str(args.concurrency),
            "PEERLY_LOAD_RECEIPT_DIRECTORY": str(output),
        }
        # No shell, credentials in argv, retries or broad test discovery. The
        # scenario's own fixture enforces loopback/_test and unique Alembic schema.
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pytest",
            "-c",
            "pyproject.toml",
            f"tests/load/scenario.py::test_root_http_backpressure_and_core_continuity[{mode}]",
            f"--junitxml={output / (mode + '.xml')}",
            cwd=root / "backend",
            env=environment,
        )
        try:
            exit_code = await process.wait()
        except asyncio.CancelledError:
            process.send_signal(signal.SIGINT)
            try:
                async with asyncio.timeout(5):
                    await process.wait()
            except TimeoutError:
                process.kill()
                await process.wait()
            raise
        results.append(
            {
                "mode": mode,
                "pytest_exit": exit_code,
                "completed_receipt_present": receipt.is_file(),
            }
        )
        if exit_code != 0:
            break
    (output / "run.json").write_text(
        json.dumps({"steps": results, "production_capacity_accepted": False}, indent=2) + "\n"
    )
    return (
        0
        if len(results) == len(modes)
        and all(
            item["pytest_exit"] == 0 and item["completed_receipt_present"] is True
            for item in results
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
