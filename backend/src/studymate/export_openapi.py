"""Deterministic enabled-auth contract export, with synthetic configuration only."""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import SecretStr

from studymate.bootstrap import create_app
from studymate.config import AiHttpConfiguration, AuthenticationConfiguration, Settings


async def build_schema() -> dict[str, object]:
    settings = Settings(
        _env_file=None,
        media=None,
        ai=AiHttpConfiguration(),
        observability=None,
        database_url=SecretStr("postgresql+asyncpg://schema:synthetic@127.0.0.1:1/schema_only"),
        authentication=AuthenticationConfiguration(
            client_id="synthetic-schema-client",
            client_secret=SecretStr("synthetic-schema-secret"),
            public_origin="https://schema.invalid",
            envelope_key=SecretStr("01" * 32),
            browser_signing_key=SecretStr("02" * 32),
            code_key=SecretStr("03" * 32),
        ),
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        schema: dict[str, object] = app.openapi()
        return schema


class ExportArguments(argparse.Namespace):
    output: Path | None = None


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write JSON to this path; otherwise stdout")
    options = ExportArguments()
    parser.parse_args(argv, namespace=options)
    rendered = (
        json.dumps(asyncio.run(build_schema()), ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    )
    if options.output is None:
        sys.stdout.write(rendered)
    else:
        options.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
