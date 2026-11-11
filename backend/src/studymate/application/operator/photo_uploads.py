"""Audited account-scoped retained photo root search and raw version history."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import (
    OperatorPrincipal,
    finish_operator,
    require_operator,
)
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.application.operator.photo_ports import (
    OperatorPhotoCursorCodec,
    OperatorPhotoFilters,
    OperatorPhotoHistoryPosition,
    OperatorPhotoHistoryWindow,
    OperatorPhotoTransaction,
    OperatorPhotoUnitOfWork,
    OperatorPhotoUploadRootPosition,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.photo_uploads import (
    MAX_OPERATOR_MEDIA_ORIGINS,
    MAX_OPERATOR_PHOTO_ATTEMPTS,
    OPERATOR_PHOTO_PAGE_SIZE,
    OperatorMediaOrigin,
    OperatorPhotoAttempt,
    OperatorPhotoUploadRevision,
    OperatorPhotoUploadRoot,
    OperatorPublishedPhotoRef,
)


@dataclass(frozen=True, slots=True)
class OperatorPhotoUploadsPage:
    account_id: UUID
    uploads: tuple[OperatorPhotoUploadRoot, ...]
    next_cursor: str | None
    anchor_created_at: datetime | None
    anchor_upload_id: UUID | None
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class OperatorPhotoHistoryPage:
    upload: OperatorPhotoUploadRoot
    revisions: tuple[OperatorPhotoUploadRevision, ...] = field(repr=False)
    next_cursor: str | None
    anchor_version: int
    observed_at: datetime
    attempts_current: tuple[OperatorPhotoAttempt, ...]
    origins: tuple[OperatorMediaOrigin, ...]
    latest_published_photo_ref: OperatorPublishedPhotoRef | None


async def audit_photo_account(
    transaction: OperatorPhotoTransaction,
    principal: OperatorPrincipal,
    account_id: UUID,
    *,
    found: bool,
) -> None:
    """Photo inspections audit their REAL account scope, never a fabricated revision UUID."""
    resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
    await transaction.save_operator_audit(
        OperatorAudit(
            uuid4(),
            principal.access,
            OperatorAction.READ_ACCOUNT,
            resource,
            (resource,) if found else (),
            await transaction.now(),
            OperatorAuditOutcome.READ if found else OperatorAuditOutcome.NOT_FOUND,
        )
    )
    await finish_operator(transaction, principal)


def validate_photo_roots(
    rows: tuple[OperatorPhotoUploadRoot, ...],
    account_id: UUID,
    filters: OperatorPhotoFilters,
    position: OperatorPhotoUploadRootPosition | None,
) -> None:
    if len(rows) > OPERATOR_PHOTO_PAGE_SIZE + 1:
        raise RuntimeError("Photo root source exceeded its bounded metadata page")
    previous = (
        (position.before_created_at, position.before_upload_id.int)
        if position is not None
        else None
    )
    for row in rows:
        key = row.created_at, row.id.int
        if (
            row.account_id != account_id
            or not filters.matches(row)
            or (previous is not None and key >= previous)
            or (
                position is not None
                and key > (position.anchor_created_at, position.anchor_upload_id.int)
            )
        ):
            raise RuntimeError(
                "Photo root source violates actual owner, filter or metadata ordering"
            )
        previous = key


@dataclass(frozen=True, slots=True)
class ReadOperatorPhotoUploads:
    unit_of_work: OperatorPhotoUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorPhotoCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        filters: OperatorPhotoFilters,
        cursor: str | None = None,
    ) -> OperatorPhotoUploadsPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.photo_account(account_id)
            if actual is None:
                await audit_photo_account(transaction, principal, account_id, found=False)
                return None
            if actual != account_id:
                raise RuntimeError("Photo root account source belongs to another requested account")
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_roots(scope, account_id, digest, cursor)
                if cursor is not None
                else None
            )
            rows = await transaction.photo_roots(account_id, filters, position)
            validate_photo_roots(rows, account_id, filters, position)
            anchor_at, anchor_id = (
                (position.anchor_created_at, position.anchor_upload_id)
                if position is not None
                else (rows[0].created_at, rows[0].id)
                if rows
                else (None, None)
            )
            visible = rows[:OPERATOR_PHOTO_PAGE_SIZE]
            continuation = None
            if len(rows) > OPERATOR_PHOTO_PAGE_SIZE:
                if anchor_at is None or anchor_id is None:
                    raise RuntimeError("Photo root source lost its actual continuation anchor")
                continuation = self.cursor_codec.encode_roots(
                    scope,
                    account_id,
                    digest,
                    OperatorPhotoUploadRootPosition(
                        anchor_at, anchor_id, visible[-1].created_at, visible[-1].id
                    ),
                )
            observed = await transaction.now()
            await audit_photo_account(transaction, principal, account_id, found=True)
            return OperatorPhotoUploadsPage(
                account_id, visible, continuation, anchor_at, anchor_id, observed
            )


@dataclass(frozen=True, slots=True)
class ReadOperatorPhotoHistory:
    unit_of_work: OperatorPhotoUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorPhotoCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        upload_id: UUID,
        cursor: str | None = None,
    ) -> OperatorPhotoHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.photo_account(account_id)
            if actual is None:
                await audit_photo_account(transaction, principal, account_id, found=False)
                return None
            if actual != account_id:
                raise RuntimeError(
                    "Photo history account source belongs to another requested account"
                )
            head = await transaction.photo_history_head(account_id, upload_id)
            if head is None:
                # The real parent ACCOUNT was inspected even when its requested child is absent.
                await audit_photo_account(transaction, principal, account_id, found=True)
                return None
            if head.upload.id != upload_id or head.upload.account_id != account_id:
                raise RuntimeError("Photo history head belongs to another actual owner or photo")
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_history(scope, account_id, upload_id, cursor)
                if cursor is not None
                else None
            )
            if position is not None and position.anchor_version > head.latest_version:
                raise InvalidOperatorCursorError
            anchor = position.anchor_version if position is not None else head.latest_version
            window = OperatorPhotoHistoryWindow(
                anchor, position.before_version if position is not None else None
            )
            rows = await transaction.photo_history_revisions(account_id, upload_id, window)
            validate_photo_revisions(rows, account_id, upload_id, window)
            visible = rows[:OPERATOR_PHOTO_PAGE_SIZE]
            continuation = (
                self.cursor_codec.encode_history(
                    scope,
                    account_id,
                    upload_id,
                    OperatorPhotoHistoryPosition(anchor, visible[-1].version),
                )
                if len(rows) > OPERATOR_PHOTO_PAGE_SIZE
                else None
            )
            attempts = await transaction.photo_attempts_current(account_id, upload_id)
            origins = await transaction.photo_origins(account_id, upload_id)
            publication = await transaction.latest_photo_publication(account_id, upload_id)
            validate_photo_metadata(attempts, origins, publication, account_id, upload_id)
            observed = await transaction.now()
            await audit_photo_account(transaction, principal, account_id, found=True)
            return OperatorPhotoHistoryPage(
                head.upload, visible, continuation, anchor, observed, attempts, origins, publication
            )


def validate_photo_revisions(
    rows: tuple[OperatorPhotoUploadRevision, ...],
    account_id: UUID,
    upload_id: UUID,
    window: OperatorPhotoHistoryWindow,
) -> None:
    if len(rows) > OPERATOR_PHOTO_PAGE_SIZE + 1:
        raise RuntimeError("Photo revision source exceeded its bounded history page")
    previous = (
        window.before_version if window.before_version is not None else window.anchor_version + 1
    )
    for row in rows:
        if (
            row.account_id != account_id
            or row.upload_id != upload_id
            or row.version > window.anchor_version
            or row.version >= previous
        ):
            raise RuntimeError(
                "Photo history source violates actual owner, photo or version ordering"
            )
        previous = row.version


def validate_photo_metadata(
    attempts: tuple[OperatorPhotoAttempt, ...],
    origins: tuple[OperatorMediaOrigin, ...],
    publication: OperatorPublishedPhotoRef | None,
    account_id: UUID,
    upload_id: UUID,
) -> None:
    if (
        len(attempts) > MAX_OPERATOR_PHOTO_ATTEMPTS
        or len({row.id for row in attempts}) != len(attempts)
        or tuple(row.number for row in attempts) != tuple(sorted({row.number for row in attempts}))
        or any(row.upload_id != upload_id for row in attempts)
    ):
        raise RuntimeError("Photo attempts violate their bounded actual upload source")
    if (
        len(origins) > MAX_OPERATOR_MEDIA_ORIGINS
        or len({row.phase for row in origins}) != len(origins)
        or any(row.upload_id != upload_id for row in origins)
    ):
        raise RuntimeError("Photo origins violate their bounded actual upload source")
    if publication is not None and (
        publication.account_id != account_id or publication.upload_id != upload_id
    ):
        raise RuntimeError("Photo publication belongs to another actual owner or upload")
