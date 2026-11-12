"""Explicit staging-only neutral photo queueing; never registration or a READY override."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import stat
import struct
import sys
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Never
from uuid import UUID, uuid5

from aiohttp import ClientError, ClientSession, ClientTimeout, FormData
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from studymate.application.media.storage import MediaStorageUnavailableError
from studymate.application.media.uploads import PROCESSING_LIFETIME, UPLOAD_LIFETIME
from studymate.bootstrap import _open_media_storage
from studymate.config import MediaWorkerSettings
from studymate.domain.media import (
    MediaObjectKind,
    MediaObjectRef,
    PhotoContentType,
    PhotoSource,
    PhotoUpload,
    PhotoUploadState,
)
from studymate.infrastructure.persistence.identity_claims import identity_lineage_banned
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.media_uploads import SqlMediaTransaction
from studymate.infrastructure.persistence.schema import MODELS

if TYPE_CHECKING:
    from studymate.application.media.storage import MediaStorage

DATABASE = "peerly_staging"
MAX_INPUT = 8192
MAX_ENTRIES = 10
MAX_JOURNAL = 1_000_000
if not MODELS:
    raise RuntimeError("Application model registry unavailable")


class PlaceholderPhotoError(ValueError):
    """Fixed public error code only; no configuration or private records."""


@dataclass(frozen=True, slots=True)
class Entry:
    account_id: UUID
    expected_photo_version: int


@dataclass(frozen=True, slots=True)
class Manifest:
    operation_id: UUID
    entries: tuple[Entry, ...]
    fingerprint: str

    def upload_id(self, entry: Entry) -> UUID:
        return uuid5(self.operation_id, f"staging-neutral-photo.v1:{entry.account_id}")


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PlaceholderPhotoError("duplicate_json_key")
        result[key] = value
    return result


def parse_manifest(raw: bytes) -> Manifest:
    if len(raw) > MAX_INPUT:
        raise PlaceholderPhotoError("input_too_large")
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or set(value) != {"operation_id", "entries"}:
        raise PlaceholderPhotoError("invalid_manifest")
    rows = value["entries"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ENTRIES:
        raise PlaceholderPhotoError("invalid_entries")
    if not isinstance(value["operation_id"], str):
        raise PlaceholderPhotoError("invalid_operation")
    entries: list[Entry] = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"account_id", "expected_photo_version"}
            or not isinstance(row["account_id"], str)
            or type(row["expected_photo_version"]) is not int
            or row["expected_photo_version"] != 0
        ):
            raise PlaceholderPhotoError("invalid_entry")
        entries.append(Entry(UUID(row["account_id"]), row["expected_photo_version"]))
    if len({entry.account_id for entry in entries}) != len(entries):
        raise PlaceholderPhotoError("duplicate_account")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return Manifest(
        UUID(value["operation_id"]), tuple(entries), hashlib.sha256(canonical).hexdigest()
    )


def neutral_png() -> bytes:
    """Deterministic generic silhouette, not a student's personal photo."""
    edge = 128
    shoulder_start = 80
    rows = bytearray()
    for y in range(edge):
        rows.append(0)
        for x in range(edge):
            head = (x - 64) ** 2 + (y - 43) ** 2 <= 20**2
            shoulders = y >= shoulder_start and (x - 64) ** 2 + (y - 121) ** 2 <= 43**2
            rows.extend((110, 120, 135) if head or shoulders else (235, 239, 244))

    def chunk(kind: bytes, content: bytes) -> bytes:
        return (
            struct.pack("!I", len(content))
            + kind
            + content
            + struct.pack("!I", zlib.crc32(kind + content))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", edge, edge, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows)))
        + chunk(b"IEND", b"")
    )


async def inspect_target(
    session: AsyncSession, manifest: Manifest, entry: Entry, source: PhotoSource
) -> PhotoUpload | None:
    account = await session.scalar(
        select(AccountRecord).where(AccountRecord.id == entry.account_id).with_for_update()
    )
    if account is None or account.deleted_at is not None or account.banned_at is not None:
        raise PlaceholderPhotoError("account_unavailable")
    binding = await session.get(InstitutionalBindingRecord, entry.account_id)
    if binding is None or binding.revoked_at is not None or binding.retired_at is not None:
        raise PlaceholderPhotoError("membership_required")
    if await identity_lineage_banned(session, entry.account_id):
        raise PlaceholderPhotoError("account_unavailable")
    transaction = SqlMediaTransaction(session)
    if await transaction.current_photo(entry.account_id) is not None:
        raise PlaceholderPhotoError("photo_already_exists")
    own = await transaction.upload(entry.account_id, manifest.upload_id(entry))
    if own is not None and (own.source != source or own.expected_photo_version != 0):
        raise PlaceholderPhotoError("operation_conflict")
    pending = await transaction._pending(entry.account_id)
    if any(upload.id != manifest.upload_id(entry) for upload in pending):
        raise PlaceholderPhotoError("other_upload_pending")
    if own is not None and own.state not in (PhotoUploadState.UPLOADING, PhotoUploadState.QUEUED):
        raise PlaceholderPhotoError("operation_not_replayable")
    return own


async def stage_upload(
    session: AsyncSession, manifest: Manifest, entry: Entry, source: PhotoSource, *, apply: bool
) -> PhotoUpload | None:
    current = await inspect_target(session, manifest, entry, source)
    if current is not None or not apply:
        return current
    transaction = SqlMediaTransaction(session)
    at = await transaction.now()
    upload = PhotoUpload(
        manifest.upload_id(entry),
        entry.account_id,
        source,
        0,
        at,
        at + UPLOAD_LIFETIME,
        at + PROCESSING_LIFETIME,
        at,
    )
    await transaction.create_upload(upload)
    return upload


async def queue_upload(
    session: AsyncSession, manifest: Manifest, upload: PhotoUpload, source: PhotoSource
) -> None:
    current = await inspect_target(session, manifest, Entry(upload.account_id, 0), source)
    if current is None:
        raise PlaceholderPhotoError("upload_missing")
    transaction = SqlMediaTransaction(session)
    queued = current.queue(await transaction.now())
    if queued.state != PhotoUploadState.QUEUED:
        raise PlaceholderPhotoError("upload_expired")
    if queued is not current:
        await transaction.save_upload(queued)


async def send_transport(storage: MediaStorage, upload: PhotoUpload, body: bytes) -> None:
    reference = MediaObjectRef(upload.id, MediaObjectKind.UPLOAD)
    access = await storage.upload_access(
        reference, upload.source.content_type.value, upload.upload_expires_at
    )
    form = FormData()
    for key, value in access.fields:
        form.add_field(key, value)
    form.add_field("file", body, filename="neutral.png", content_type="image/png")
    async with (
        ClientSession(timeout=ClientTimeout(total=25)) as client,
        client.post(access.url, data=form, allow_redirects=False) as response,
    ):
        if response.status not in (200, 201, 204):
            raise PlaceholderPhotoError("transport_upload_failed")
    if await storage.read(reference) != body:
        raise PlaceholderPhotoError("transport_identity_failed")


def append_journal(path: Path, record: dict[str, object]) -> None:
    """Root-only external provenance, persisted before any mutation; never telemetry."""
    if os.geteuid() != 0:
        raise PlaceholderPhotoError("root_required")
    parent = path.parent.stat()
    if parent.st_uid != 0 or parent.st_mode & 0o022:
        raise PlaceholderPhotoError("unsafe_journal_directory")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o077:
            raise PlaceholderPhotoError("unsafe_journal")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if metadata.st_size > MAX_JOURNAL:
            raise PlaceholderPhotoError("journal_too_large")
        previous = os.read(descriptor, MAX_JOURNAL + 1)
        for line in previous.splitlines():
            prior = json.loads(line)
            if not isinstance(prior, dict) or any(
                prior.get(key) != record.get(key)
                for key in ("operation_id", "manifest_sha256", "artifact_sha256")
            ):
                raise PlaceholderPhotoError("journal_operation_conflict")
        encoded = (
            json.dumps({**record, "recorded_at": datetime.now(UTC).isoformat()}, sort_keys=True)
            + "\n"
        ).encode()
        with os.fdopen(descriptor, "ab", closefd=False) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


async def execute(
    sessions: async_sessionmaker[AsyncSession],
    manifest: Manifest,
    source: PhotoSource,
    *,
    expected_database: str,
    apply: bool,
) -> tuple[PhotoUpload | None, ...]:
    async with sessions.begin() as session:
        if await session.scalar(select(func.current_database())) != expected_database:
            raise PlaceholderPhotoError("wrong_database")
        # Acquire accounts in stable order; recheck the complete batch before writes.
        ordered = sorted(manifest.entries, key=lambda item: item.account_id)
        for entry in ordered:
            await inspect_target(session, manifest, entry, source)
        return tuple(
            [await stage_upload(session, manifest, entry, source, apply=apply) for entry in ordered]
        )


async def run(manifest: Manifest, *, apply: bool, journal: Path | None) -> dict[str, object]:
    settings = MediaWorkerSettings()
    url = settings.database_url.get_secret_value()
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or parsed.database != DATABASE:
        raise PlaceholderPhotoError("wrong_database_configuration")
    body = await asyncio.to_thread(neutral_png)
    source = PhotoSource(len(body), hashlib.sha256(body).digest(), PhotoContentType.PNG)
    record: dict[str, object] = {
        "operation_id": str(manifest.operation_id),
        "manifest_sha256": manifest.fingerprint,
        "artifact_sha256": source.sha256.hex(),
        "kind": "owner-approved-staging-neutral-photo.v1",
        "helper_sha256": hashlib.sha256(
            await asyncio.to_thread(Path(__file__).read_bytes)
        ).hexdigest(),
        "entries": [
            {"account_id": str(entry.account_id), "upload_id": str(manifest.upload_id(entry))}
            for entry in manifest.entries
        ],
    }
    engine = create_async_engine(
        url,
        pool_size=1,
        max_overflow=0,
        pool_timeout=5,
        connect_args={"timeout": 5, "command_timeout": 10},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with asyncio.timeout(120):
            await execute(sessions, manifest, source, expected_database=DATABASE, apply=False)
            if apply:
                if journal is None:
                    raise PlaceholderPhotoError("journal_required")
                await asyncio.to_thread(append_journal, journal, {**record, "phase": "prepared"})
                uploads = await execute(
                    sessions, manifest, source, expected_database=DATABASE, apply=True
                )
                async with _open_media_storage(settings.media) as storage:
                    for upload in uploads:
                        if upload is None:
                            raise PlaceholderPhotoError("upload_missing")
                        if upload.state == PhotoUploadState.QUEUED:
                            continue
                        await send_transport(storage, upload, body)
                        async with sessions.begin() as session:
                            await queue_upload(session, manifest, upload, source)
                        await asyncio.to_thread(
                            append_journal,
                            journal,
                            {
                                **record,
                                "phase": "queued",
                                "upload_id": str(upload.id),
                            },
                        )
            return {
                "status": "queued" if apply else "planned",
                "entries": len(manifest.entries),
                "operation_id": str(manifest.operation_id),
                "manifest_sha256": manifest.fingerprint,
                "artifact_sha256": source.sha256.hex(),
                "registration_changed": False,
                "photo_ready_fabricated": False,
            }
    finally:
        await engine.dispose()


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise PlaceholderPhotoError("invalid_arguments")


def main() -> int:
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument("command", choices=("plan", "apply"))
        parser.add_argument("--journal", type=Path)
        arguments = parser.parse_args()
        manifest = parse_manifest(sys.stdin.buffer.read(MAX_INPUT + 1))
        result = asyncio.run(
            run(manifest, apply=arguments.command == "apply", journal=arguments.journal)
        )
    except PlaceholderPhotoError as error:
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
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
