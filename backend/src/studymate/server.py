"""API process entrypoint with content-free runtime diagnostics."""

from argparse import ArgumentParser
from collections.abc import Sequence

import uvicorn

from studymate.infrastructure.observability.logging import (
    configure_logging,
    logging_configuration,
)


def main(arguments: Sequence[str] | None = None) -> None:
    parser = ArgumentParser()
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    options = parser.parse_args(arguments)
    configure_logging()
    uvicorn.run(
        "studymate.bootstrap:create_app",
        factory=True,
        host=options.host,
        port=options.port,
        reload=options.reload,
        access_log=False,
        log_config=logging_configuration(),
    )


if __name__ == "__main__":
    main()
