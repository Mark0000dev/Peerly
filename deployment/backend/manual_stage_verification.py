"""Explicit owner-only staging membership override; never an OTP or public API."""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Never
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from studymate.domain.identity import StudentEmail
from studymate.infrastructure.changes.staging import stage_change_outbox
from studymate.infrastructure.persistence.email_models import (
    EmailChallengeRecord,
    EmailDeliveryRecord,
)
from studymate.infrastructure.persistence.identity_claims import (
    email_lineage_banned,
    identity_lineage_banned,
)
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.infrastructure.persistence.schema import MODELS

EXPECTED_DATABASE = "peerly_staging"
MAX_INPUT = 16384
MAX_ENTRIES = 20
if not MODELS:  # Register real FK targets; never create or migrate a schema.
    raise RuntimeError("Application model registry is unavailable")


class ManualVerificationError(ValueError):
    """Only a fixed nonprivate code can cross the CLI boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class Entry:
    account_id: UUID
    email: str = field(repr=False)
    challenge_id: UUID | None


@dataclass(frozen=True, slots=True)
class Manifest:
    operation_id: UUID
    performed_by: str
    entries: tuple[Entry, ...]
    fingerprint: str


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ManualVerificationError("duplicate_json_key")
        result[key] = value
    return result


def parse_manifest(raw: bytes) -> Manifest:
    if len(raw) > MAX_INPUT:
        raise ManualVerificationError("input_too_large")
    value = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(value, dict) or set(value) != {
        "operation_id",
        "performed_by",
        "entries",
    }:
        raise ManualVerificationError("invalid_manifest")
    reference = value["performed_by"]
    if not isinstance(reference, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,38}", reference):
        raise ManualVerificationError("invalid_performed_by")
    if not isinstance(value["operation_id"], str):
        raise ManualVerificationError("invalid_operation")
    operation = UUID(value["operation_id"])
    rows = value["entries"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ENTRIES:
        raise ManualVerificationError("invalid_entries")
    entries: list[Entry] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "account_id",
            "email",
            "challenge_id",
        }:
            raise ManualVerificationError("invalid_entry")
        if not isinstance(row["account_id"], str) or not isinstance(row["email"], str):
            raise ManualVerificationError("invalid_entry")
        if row["challenge_id"] is not None and not isinstance(row["challenge_id"], str):
            raise ManualVerificationError("invalid_entry")
        email = StudentEmail(row["email"]).value
        if email != row["email"]:
            raise ManualVerificationError("noncanonical_email")
        account_id = UUID(row["account_id"])
        challenge_id = UUID(row["challenge_id"]) if row["challenge_id"] is not None else None
        if challenge_id is None and email != placeholder(account_id):
            raise ManualVerificationError("invalid_placeholder")
        entries.append(Entry(account_id, email, challenge_id))
    if (
        len({entry.account_id for entry in entries}) != len(entries)
        or len({entry.email for entry in entries}) != len(entries)
        or len({entry.challenge_id for entry in entries if entry.challenge_id is not None})
        != sum(entry.challenge_id is not None for entry in entries)
    ):
        raise ManualVerificationError("duplicate_target")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return Manifest(
        operation,
        reference,
        tuple(sorted(entries, key=lambda entry: entry.account_id)),
        hashlib.sha256(canonical).hexdigest(),
    )


def placeholder(account_id: UUID) -> str:
    return f"peerly-stage-{account_id.hex}@mail.apu.edu.my"


def occurrence(manifest: Manifest, entry: Entry) -> str:
    source = (
        "p"
        if entry.challenge_id is None
        else "c" + base64.urlsafe_b64encode(entry.challenge_id.bytes).decode().rstrip("=")
    )
    return f"smv1:{manifest.operation_id.hex}:{source}:{manifest.performed_by}"


@dataclass(frozen=True, slots=True)
class Target:
    entry: Entry
    challenge: EmailChallengeRecord | None
    prior: ProductEventRecord | None
    already_verified: bool


async def requested_challenge(session: AsyncSession, entry: Entry) -> EmailChallengeRecord | None:
    latest = await session.scalar(
        select(EmailChallengeRecord.id)
        .where(EmailChallengeRecord.account_id == entry.account_id)
        .order_by(EmailChallengeRecord.created_at.desc(), EmailChallengeRecord.id.desc())
        .limit(1)
    )
    challenge = None
    if entry.challenge_id is None:
        if latest is not None or entry.email != placeholder(entry.account_id):
            raise ManualVerificationError("placeholder_requires_no_email_challenges")
    else:
        challenge = await session.get(
            EmailChallengeRecord, entry.challenge_id, with_for_update=True
        )
        if (
            challenge is None
            or challenge.account_id != entry.account_id
            or challenge.email != entry.email
        ):
            raise ManualVerificationError("submitted_email_mismatch")
        if latest != entry.challenge_id:
            raise ManualVerificationError("stale_challenge")
    return challenge


async def inspect_target(session: AsyncSession, manifest: Manifest, entry: Entry) -> Target:
    account = await session.get(AccountRecord, entry.account_id)
    if account is None or account.deleted_at is not None:
        raise ManualVerificationError("account_unavailable")
    if account.banned_at is not None or await identity_lineage_banned(session, entry.account_id):
        raise ManualVerificationError("account_restricted")
    google = await session.scalar(
        select(ExternalIdentityRecord.id).where(
            ExternalIdentityRecord.account_id == entry.account_id,
            ExternalIdentityRecord.retired_at.is_(None),
        )
    )
    if google is None:
        raise ManualVerificationError("google_identity_required")
    challenge = await requested_challenge(session, entry)
    if await email_lineage_banned(session, entry.email):
        raise ManualVerificationError("email_restricted")
    prior = await session.scalar(
        select(ProductEventRecord).where(
            ProductEventRecord.account_id == entry.account_id,
            ProductEventRecord.kind == "auth.email_confirmed",
            ProductEventRecord.occurrence_key == occurrence(manifest, entry),
        )
    )
    binding = await session.get(InstitutionalBindingRecord, entry.account_id)
    if binding is not None:
        if (
            binding.email != entry.email
            or binding.revoked_at is not None
            or binding.retired_at is not None
        ):
            raise ManualVerificationError("binding_conflict")
        if prior is not None and binding.verified_at != prior.occurred_at:
            raise ManualVerificationError("provenance_conflict")
        return Target(entry, challenge, prior, prior is None)
    if prior is not None:
        raise ManualVerificationError("provenance_conflict")
    if challenge is not None and (
        challenge.consumed_at is not None or challenge.superseded_at is not None
    ):
        raise ManualVerificationError("challenge_not_pending")
    owner = await session.scalar(
        select(InstitutionalBindingRecord.account_id).where(
            InstitutionalBindingRecord.email == entry.email,
            InstitutionalBindingRecord.retired_at.is_(None),
        )
    )
    if owner is not None:
        raise ManualVerificationError("email_already_claimed")
    return Target(entry, challenge, None, False)


async def grant(session: AsyncSession, manifest: Manifest, target: Target, at: datetime) -> UUID:
    entry = target.entry
    session.add(
        InstitutionalBindingRecord(account_id=entry.account_id, email=entry.email, verified_at=at)
    )
    await session.flush()
    event = ProductEventRecord(
        id=uuid4(),
        account_id=entry.account_id,
        kind="auth.email_confirmed",
        occurrence_key=occurrence(manifest, entry),
        schema_version=1,
        occurred_at=at,
    )
    session.add(event)
    await session.flush()
    await stage_change_outbox(session, event)
    # Administrator attestation is NOT foreground user activity or OTP consumption.
    if target.challenge is not None:
        target.challenge.superseded_at = at
        target.challenge.code_digest = None
        await session.execute(
            update(EmailDeliveryRecord)
            .where(
                EmailDeliveryRecord.challenge_id == entry.challenge_id,
                EmailDeliveryRecord.status.in_(("queued", "inflight")),
            )
            .values(status="cancelled", sealed_envelope=None, lease_until=None)
        )
    return event.id


async def execute(
    session: AsyncSession, manifest: Manifest, *, apply: bool, expected_database: str
) -> dict[str, object]:
    """Caller owns one transaction; tests supply only their disposable DB name."""
    if await session.scalar(select(func.current_database())) != expected_database:
        raise ManualVerificationError("wrong_database")
    await session.execute(
        select(AccountRecord.id)
        .where(
            AccountRecord.id.in_(entry.account_id for entry in manifest.entries),
        )
        .order_by(AccountRecord.id)
        .with_for_update()
    )
    targets = tuple([await inspect_target(session, manifest, entry) for entry in manifest.entries])
    existing = tuple(
        await session.scalars(
            select(ProductEventRecord).where(
                ProductEventRecord.kind == "auth.email_confirmed",
                ProductEventRecord.occurrence_key.like(f"smv1:{manifest.operation_id.hex}:%"),
            )
        )
    )
    expected = {
        (target.entry.account_id, occurrence(manifest, target.entry))
        for target in targets
        if not target.already_verified
    }
    if existing and {(row.account_id, row.occurrence_key) for row in existing} != expected:
        raise ManualVerificationError("operation_conflict")
    at = await session.scalar(select(func.clock_timestamp()))
    if not isinstance(at, datetime):
        raise ManualVerificationError("database_clock_unavailable")
    events: list[str] = []
    eligible = 0
    for target in targets:
        if target.prior is not None:
            events.append(str(target.prior.id))
        elif not target.already_verified:
            eligible += 1
            if apply:
                events.append(str(await grant(session, manifest, target, at)))
    await session.flush()
    return {
        "status": "applied" if apply else "planned",
        "operation_id": str(manifest.operation_id),
        "manifest_sha256": manifest.fingerprint,
        "entries": len(targets),
        "eligible": eligible,
        "already_verified": sum(target.already_verified for target in targets),
        "replayed": sum(target.prior is not None for target in targets),
        "applied": eligible if apply else 0,
        "event_ids": events,
        "otp_consumed": False,
        "synthetic_placeholders": sum(target.entry.challenge_id is None for target in targets),
    }


async def run(manifest: Manifest, apply: bool) -> dict[str, object]:
    url = os.environ.get("DATABASE_URL", "")
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or parsed.database != EXPECTED_DATABASE:
        raise ManualVerificationError("wrong_database_configuration")
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
                return await execute(
                    session, manifest, apply=apply, expected_database=EXPECTED_DATABASE
                )
    finally:
        await engine.dispose()


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        del message
        raise ManualVerificationError("invalid_arguments")


def main() -> int:
    try:
        parser = SafeParser(description=__doc__)
        parser.add_argument("command", choices=("plan", "apply"))
        parser.add_argument(
            "--input",
            default="-",
            help="Private JSON file or - for stdin; never inline JSON",
        )
        options = parser.parse_args()
        if options.input == "-":
            raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        else:
            descriptor = os.open(Path(options.input), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                import stat

                metadata = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_mode & 0o077
                    or metadata.st_uid not in {0, os.geteuid()}
                ):
                    raise ManualVerificationError("unsafe_input_file")
                raw = os.read(descriptor, MAX_INPUT + 1)
            finally:
                os.close(descriptor)
        result = asyncio.run(run(parse_manifest(raw), options.command == "apply"))
    except ManualVerificationError as error:
        result = {"status": "rejected", "code": error.code}
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
