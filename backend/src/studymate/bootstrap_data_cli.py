"""Explicit owner-file schema/validate/apply. Never an automatic application seed."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Never

from studymate.application.bootstrap_data.apply import (
    BootstrapConflictError,
    MissingPublishedPoliciesError,
)
from studymate.application.bootstrap_data.ports import (
    BootstrapDatabaseConfigurationError,
    BootstrapDatabaseOperationError,
)
from studymate.application.errors import StorageUnavailableError
from studymate.presentation.bootstrap_data.inputs import (
    BootstrapInput,
    BootstrapInputError,
    load_input,
)


class BootstrapUsageError(Exception):
    pass


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message  # argparse's raw message can contain arbitrary supplied argument values.
        raise BootstrapUsageError


def emit(value: object) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n")


def parser() -> argparse.ArgumentParser:
    result = SafeParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("schema", help="Print the closed JSON schema; no settings/database")
    for name in ("validate", "apply"):
        command = subcommands.add_parser(name)
        command.add_argument("file", help="Explicit owner-authored regular UTF8 JSON file")
    return result


async def dispatch(options: argparse.Namespace) -> int:
    command: object = options.command
    if command == "schema":
        emit(BootstrapInput.model_json_schema())
        return 0
    filename: object = getattr(options, "file", None)
    if not isinstance(filename, str):
        raise BootstrapUsageError
    batch = await load_input(Path(filename))
    if command == "validate":
        emit(
            {
                "status": "valid",
                "schema_version": 1,
                "policy_count": len(batch.policies),
                "subject_count": len(batch.catalogue.subjects)
                if batch.catalogue is not None
                else 0,
                "alias_count": batch.catalogue.alias_count if batch.catalogue is not None else 0,
            }
        )
        return 0
    if command != "apply":
        raise BootstrapUsageError
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise BootstrapDatabaseConfigurationError
    # Offline branches never import settings, SQLAlchemy, ORM metadata or DB resources.
    from studymate.bootstrap import apply_bootstrap_reference_data

    result = await apply_bootstrap_reference_data(batch, database_url)
    changed = result.policies_created > 0 or (
        result.catalogue.version is not None and not result.catalogue.replayed
    )
    emit(
        {
            "status": "applied" if changed else "unchanged",
            "policies_created": result.policies_created,
            "policies_unchanged": result.policies_unchanged,
            "subjects_created": result.catalogue.created,
            "subjects_unchanged": result.catalogue.unchanged,
            "catalogue_version": result.catalogue.version,
            "catalogue_replayed": result.catalogue.replayed,
            "terms_id": str(result.terms.id),
            "terms_version": result.terms.version.value,
            "privacy_id": str(result.privacy.id),
            "privacy_version": result.privacy.version.value,
        }
    )
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(dispatch(parser().parse_args(arguments)))
    except (BootstrapUsageError, BootstrapInputError, BootstrapDatabaseConfigurationError) as error:
        if isinstance(error, BootstrapUsageError):
            code = "invalid_arguments"
        elif isinstance(error, BootstrapDatabaseConfigurationError):
            code = "database_configuration"
        else:
            code = error.code.value
        emit({"status": "error", "code": code})
        return 2
    except BootstrapConflictError as error:
        emit(
            {
                "status": "conflict",
                "code": error.code.value,
                "resource_id": str(error.resource_id) if error.resource_id is not None else None,
            }
        )
        return 3
    except MissingPublishedPoliciesError:
        emit({"status": "error", "code": "current_policy_pair_required"})
        return 4
    except (BootstrapDatabaseOperationError, StorageUnavailableError, TimeoutError) as error:
        code = (
            "storage_unavailable"
            if isinstance(error, StorageUnavailableError)
            else "database_error"
        )
        emit({"status": "error", "code": code})
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
