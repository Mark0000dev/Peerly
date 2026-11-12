"""Owner-only staging recovery for an existing uploaded photo; no public/session bypass."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from aiohttp import ClientError
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from studymate.application.media.storage import MediaStorageUnavailableError
from studymate.bootstrap import _open_media_storage
from studymate.config import MediaWorkerSettings
from studymate.domain.media import MediaObjectKind, MediaObjectRef, PhotoUpload, PhotoUploadState
from studymate.infrastructure.persistence.identity_claims import identity_lineage_banned
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.media_uploads import SqlMediaTransaction
from studymate.infrastructure.persistence.schema import MODELS

DATABASE = "peerly_staging"
MAX_INPUT = 4096
if not MODELS:
    raise RuntimeError("Application model registry unavailable")


class QueueRecoveryError(ValueError):
    """Fixed nonprivate error code only."""


@dataclass(frozen=True, slots=True)
class Recovery:
    operation_id: UUID
    account_id: UUID
    upload_id: UUID
    expected_upload_version: int


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise QueueRecoveryError("duplicate_json_key")
        result[key] = value
    return result


def parse(raw: bytes) -> Recovery:
    if len(raw) > MAX_INPUT:
        raise QueueRecoveryError("input_too_large")
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or set(value) != {
        "operation_id",
        "account_id",
        "upload_id",
        "expected_upload_version",
    }:
        raise QueueRecoveryError("invalid_manifest")
    if type(value["expected_upload_version"]) is not int or value["expected_upload_version"] < 1:
        raise QueueRecoveryError("invalid_version")
    if not all(isinstance(value[key], str) for key in ("operation_id", "account_id", "upload_id")):
        raise QueueRecoveryError("invalid_identity")
    return Recovery(
        UUID(value["operation_id"]),
        UUID(value["account_id"]),
        UUID(value["upload_id"]),
        value["expected_upload_version"],
    )


async def inspect(session: AsyncSession, request: Recovery) -> PhotoUpload:
    account = await session.scalar(
        select(AccountRecord)
        .where(
            AccountRecord.id == request.account_id,
        )
        .with_for_update()
    )
    if account is None or account.deleted_at is not None or account.banned_at is not None:
        raise QueueRecoveryError("account_unavailable")
    binding = await session.get(InstitutionalBindingRecord, request.account_id)
    if binding is None or binding.revoked_at is not None or binding.retired_at is not None:
        raise QueueRecoveryError("membership_required")
    if await identity_lineage_banned(session, request.account_id):
        raise QueueRecoveryError("account_unavailable")
    transaction = SqlMediaTransaction(session)
    upload = await transaction.upload(request.account_id, request.upload_id)
    if upload is None or upload.version != request.expected_upload_version:
        raise QueueRecoveryError("upload_version_conflict")
    if upload.state != PhotoUploadState.UPLOADING:
        raise QueueRecoveryError("not_uploading")
    photo = await transaction.current_photo(request.account_id)
    if (photo.version if photo is not None else 0) != upload.expected_photo_version:
        raise QueueRecoveryError("photo_version_conflict")
    if upload.expire(await transaction.now()) is not upload:
        raise QueueRecoveryError("upload_expired")
    return upload


async def queue(session: AsyncSession, request: Recovery, original: PhotoUpload) -> None:
    current = await inspect(session, request)
    if current != original:
        raise QueueRecoveryError("upload_changed")
    transaction = SqlMediaTransaction(session)
    queued = current.queue(await transaction.now())
    if queued.state != PhotoUploadState.QUEUED:
        raise QueueRecoveryError("upload_expired")
    await transaction.save_upload(queued)


def journal(path: Path, record: dict[str, object]) -> None:
    if os.geteuid() != 0:
        raise QueueRecoveryError("root_required")
    parent = path.parent.stat()
    if parent.st_uid != 0 or parent.st_mode & 0o022:
        raise QueueRecoveryError("unsafe_journal_directory")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o077:
            raise QueueRecoveryError("unsafe_journal")
        with os.fdopen(descriptor, "ab", closefd=False) as stream:
            stream.write(
                (
                    json.dumps({**record, "recorded_at": datetime.now(UTC).isoformat()}) + "\n"
                ).encode()
            )
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


async def run(request: Recovery, path: Path, *, apply: bool) -> dict[str, object]:
    settings = MediaWorkerSettings()
    url = settings.database_url.get_secret_value()
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or parsed.database != DATABASE:
        raise QueueRecoveryError("wrong_database_configuration")
    engine = create_async_engine(
        url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=5,
        connect_args={"timeout": 5, "command_timeout": 10},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with asyncio.timeout(90):
            async with sessions.begin() as session:
                if await session.scalar(select(func.current_database())) != DATABASE:
                    raise QueueRecoveryError("wrong_database")
                upload = await inspect(session, request)
            async with _open_media_storage(settings.media) as storage:
                body = await storage.read(MediaObjectRef(upload.id, MediaObjectKind.UPLOAD))
            if (
                len(body) != upload.source.size
                or hashlib.sha256(body).digest() != upload.source.sha256
            ):
                raise QueueRecoveryError("source_identity_failed")
            if apply:
                record: dict[str, object] = {
                    "kind": "owner-approved-staging-existing-photo-queue.v1",
                    "operation_id": str(request.operation_id),
                    "account_id": str(request.account_id),
                    "upload_id": str(request.upload_id),
                    "expected_upload_version": request.expected_upload_version,
                    "source_sha256": upload.source.sha256.hex(),
                    "helper_sha256": hashlib.sha256(
                        await asyncio.to_thread(Path(__file__).read_bytes)
                    ).hexdigest(),
                }
                await asyncio.to_thread(journal, path, {**record, "phase": "prepared"})
                async with sessions.begin() as session:
                    await queue(session, request, upload)
                await asyncio.to_thread(journal, path, {**record, "phase": "queued"})
            return {
                "status": "queued" if apply else "planned",
                "operation_id": str(request.operation_id),
                "source_verified": True,
                "registration_changed": False,
            }
    finally:
        await engine.dispose()


def main() -> int:
    try:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("command", choices=("plan", "apply"))
        parser.add_argument("--journal", required=True, type=Path)
        arguments = parser.parse_args()
        result = asyncio.run(
            run(
                parse(sys.stdin.buffer.read(MAX_INPUT + 1)),
                arguments.journal,
                apply=arguments.command == "apply",
            )
        )
    except QueueRecoveryError as error:
        sys.stdout.write(json.dumps({"status": "rejected", "code": str(error)}) + "\n")
        return 1
    except (
        ValueError,
        OSError,
        TimeoutError,
        SQLAlchemyError,
        ClientError,
        MediaStorageUnavailableError,
    ):
        sys.stdout.write(
            json.dumps({"status": "rejected", "code": "configuration_or_io_failed"}) + "\n"
        )
        return 1
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
