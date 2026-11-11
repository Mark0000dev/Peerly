"""Owner-operated explicit operator assignment, outside the public authentication API."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
import sys
from dataclasses import dataclass
from typing import Never
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from studymate.infrastructure.operator.models import (
    OperatorAccessRecord,
    OperatorAccessRevisionRecord,
)
from studymate.infrastructure.persistence.identity_claims import identity_lineage_banned
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
)
from studymate.infrastructure.persistence.schema import MODELS

MAX_INPUT = 4096
MAX_DATABASE_LENGTH = 63
MAX_VERSION = 2147483647
if not MODELS:
    raise RuntimeError("Application model registry is unavailable")


class OperatorAssignmentError(ValueError):
    """A fixed nonprivate rejection code, without database or manifest contents."""


@dataclass(frozen=True, slots=True)
class Assignment:
    database: str
    performed_by: UUID
    account_id: UUID
    expected_version: int
    active: bool


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise OperatorAssignmentError("duplicate_json_key")
        result[key] = value
    return result


def parse_manifest(raw: bytes) -> Assignment:
    if len(raw) > MAX_INPUT:
        raise OperatorAssignmentError("input_too_large")
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or set(value) != {
        "database",
        "performed_by",
        "account_id",
        "expected_version",
        "active",
    }:
        raise OperatorAssignmentError("invalid_manifest")
    database = value["database"]
    if not isinstance(database, str) or not database or len(database) > MAX_DATABASE_LENGTH:
        raise OperatorAssignmentError("invalid_database")
    if not isinstance(value["performed_by"], str) or not isinstance(value["account_id"], str):
        raise OperatorAssignmentError("invalid_account")
    version = value["expected_version"]
    if type(version) is not int or not 0 <= version < MAX_VERSION:
        raise OperatorAssignmentError("invalid_version")
    if not isinstance(value["active"], bool):
        raise OperatorAssignmentError("invalid_state")
    try:
        performed_by = UUID(value["performed_by"])
        account_id = UUID(value["account_id"])
    except ValueError as error:
        raise OperatorAssignmentError("invalid_account") from error
    return Assignment(database, performed_by, account_id, version, value["active"])


async def live_google_account(session: AsyncSession, account: AccountRecord) -> None:
    if account.deleted_at is not None or account.banned_at is not None:
        raise OperatorAssignmentError("account_unavailable")
    identity = await session.scalar(
        select(ExternalIdentityRecord.id).where(
            ExternalIdentityRecord.account_id == account.id,
            ExternalIdentityRecord.retired_at.is_(None),
            ExternalIdentityRecord.issuer == "https://accounts.google.com",
        )
    )
    if identity is None or await identity_lineage_banned(session, account.id):
        raise OperatorAssignmentError("google_identity_unavailable")


async def inspect_assignment(
    session: AsyncSession, command: Assignment
) -> OperatorAccessRevisionRecord | None:
    database = await session.scalar(select(func.current_database()))
    if database != command.database:
        raise OperatorAssignmentError("wrong_database")
    ids = sorted({command.performed_by, command.account_id})
    rows = (
        await session.scalars(
            select(AccountRecord)
            .where(AccountRecord.id.in_(ids))
            .order_by(AccountRecord.id)
            .with_for_update()
        )
    ).all()
    accounts = {row.id: row for row in rows}
    if len(accounts) != len(ids):
        raise OperatorAssignmentError("account_missing")
    await live_google_account(session, accounts[command.performed_by])
    if command.active:
        await live_google_account(session, accounts[command.account_id])
    access = await session.get(OperatorAccessRecord, command.account_id, with_for_update=True)
    current = None
    if access is not None:
        current = await session.get(
            OperatorAccessRevisionRecord, (command.account_id, access.current_version)
        )
        if current is None:
            raise OperatorAssignmentError("invalid_access_source")
    version = current.version if current is not None else 0
    if version != command.expected_version:
        raise OperatorAssignmentError("stale_version")
    if current is None and not command.active:
        raise OperatorAssignmentError("no_assignment_to_revoke")
    if current is not None and current.active == command.active:
        raise OperatorAssignmentError("already_in_requested_state")
    return current


async def execute(session: AsyncSession, command: Assignment, *, apply: bool) -> dict[str, object]:
    """Caller owns commit/rollback; no returned receipt is a committed result yet."""
    current = await inspect_assignment(session, command)
    version = command.expected_version + 1
    if apply:
        changed_at = await session.scalar(select(func.clock_timestamp()))
        if current is None:
            session.add(
                OperatorAccessRecord(account_id=command.account_id, current_version=version)
            )
            # Immediate revision -> root FK; root -> revision is genuinely deferred.
            await session.flush()
        session.add(
            OperatorAccessRevisionRecord(
                account_id=command.account_id,
                version=version,
                active=command.active,
                changed_at=changed_at,
                changed_by_id=command.performed_by,
            )
        )
        await session.flush()
        access = await session.get(OperatorAccessRecord, command.account_id)
        if access is None:
            raise OperatorAssignmentError("invalid_access_source")
        access.current_version = version
        await session.flush()
    return {
        "status": "applied" if apply else "planned",
        "account_id": str(command.account_id),
        "performed_by": str(command.performed_by),
        "previous_version": command.expected_version,
        "resulting_version": version,
        "active": command.active,
        "audit_source": "operator_access_revisions",
    }


def read_input(path: str) -> bytes:
    if path == "-":
        return sys.stdin.buffer.read(MAX_INPUT + 1)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_mode & 0o077
            or metadata.st_uid not in {0, os.geteuid()}
        ):
            raise OperatorAssignmentError("unsafe_input_file")
        return os.read(descriptor, MAX_INPUT + 1)
    finally:
        os.close(descriptor)


async def run(command: Assignment, *, apply: bool) -> dict[str, object]:
    url = os.environ.get("DATABASE_URL", "")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or parsed.database != command.database:
        raise OperatorAssignmentError("wrong_database_configuration")
    engine = create_async_engine(
        url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=5,
        connect_args={"timeout": 5, "command_timeout": 10},
    )
    try:
        async with asyncio.timeout(30):
            async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
                return await execute(session, command, apply=apply)
    finally:
        await engine.dispose()


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise OperatorAssignmentError("invalid_arguments")


def main() -> int:
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument("command", choices=("plan", "apply"))
        parser.add_argument("--input", default="-", help="Private JSON file or stdin (-)")
        options = parser.parse_args()
        result = asyncio.run(
            run(parse_manifest(read_input(options.input)), apply=options.command == "apply")
        )
    except OperatorAssignmentError as error:
        result = {"status": "rejected", "code": str(error)}
        code = 1
    except (ValueError, OSError, SQLAlchemyError, TimeoutError):
        result = {"status": "rejected", "code": "invalid_input_or_storage_unavailable"}
        code = 1
    else:
        code = 0
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
