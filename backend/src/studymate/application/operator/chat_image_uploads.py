"""Audited account-scoped retained chat image root search and raw version history."""

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
from studymate.application.operator.chat_image_ports import (
    OperatorChatImageCursorCodec,
    OperatorChatImageFilters,
    OperatorChatImageHistoryPosition,
    OperatorChatImageHistoryWindow,
    OperatorChatImageTransaction,
    OperatorChatImageUnitOfWork,
    OperatorChatImageUploadRootPosition,
)
from studymate.application.operator.cursors import InvalidOperatorCursorError, OperatorCursorScope
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.chat_image_uploads import (
    MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS,
    OPERATOR_CHAT_IMAGE_PAGE_SIZE,
    OperatorChatImageAttempt,
    OperatorChatImageMatchingOperation,
    OperatorChatImageUploadRevision,
    OperatorChatImageUploadRoot,
)


@dataclass(frozen=True, slots=True)
class OperatorChatImageUploadsPage:
    account_id: UUID
    uploads: tuple[OperatorChatImageUploadRoot, ...]
    next_cursor: str | None
    anchor_created_at: datetime | None
    anchor_image_id: UUID | None
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class OperatorChatImageHistoryPage:
    upload: OperatorChatImageUploadRoot
    revisions: tuple[OperatorChatImageUploadRevision, ...] = field(repr=False)
    next_cursor: str | None
    anchor_version: int
    observed_at: datetime
    attempts_current: tuple[OperatorChatImageAttempt, ...]
    matching_client_operation: OperatorChatImageMatchingOperation | None


async def audit_chat_image_account(
    transaction: OperatorChatImageTransaction,
    principal: OperatorPrincipal,
    account_id: UUID,
    *,
    found: bool,
) -> None:
    """Chat image inspections audit their REAL account scope, never a fabricated revision UUID."""
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


def validate_chat_image_roots(
    rows: tuple[OperatorChatImageUploadRoot, ...],
    account_id: UUID,
    filters: OperatorChatImageFilters,
    position: OperatorChatImageUploadRootPosition | None,
) -> None:
    if len(rows) > OPERATOR_CHAT_IMAGE_PAGE_SIZE + 1:
        raise RuntimeError("Chat image root source exceeded its bounded metadata page")
    previous = (
        (position.before_created_at, position.before_image_id.int) if position is not None else None
    )
    for row in rows:
        key = row.created_at, row.id.int
        if (
            row.account_id != account_id
            or not filters.matches(row)
            or (previous is not None and key >= previous)
            or (
                position is not None
                and key > (position.anchor_created_at, position.anchor_image_id.int)
            )
        ):
            raise RuntimeError(
                "Chat image root source violates actual owner, filter or metadata ordering"
            )
        previous = key


@dataclass(frozen=True, slots=True)
class ReadOperatorChatImageUploads:
    unit_of_work: OperatorChatImageUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorChatImageCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        filters: OperatorChatImageFilters,
        cursor: str | None = None,
    ) -> OperatorChatImageUploadsPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.chat_image_account(account_id)
            if actual is None:
                await audit_chat_image_account(transaction, principal, account_id, found=False)
                return None
            if actual != account_id:
                raise RuntimeError(
                    "Chat image root account source belongs to another requested account"
                )
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_roots(scope, account_id, digest, cursor)
                if cursor is not None
                else None
            )
            rows = await transaction.chat_image_roots(account_id, filters, position)
            validate_chat_image_roots(rows, account_id, filters, position)
            anchor_at, anchor_id = (
                (position.anchor_created_at, position.anchor_image_id)
                if position is not None
                else (rows[0].created_at, rows[0].id)
                if rows
                else (None, None)
            )
            visible = rows[:OPERATOR_CHAT_IMAGE_PAGE_SIZE]
            continuation = None
            if len(rows) > OPERATOR_CHAT_IMAGE_PAGE_SIZE:
                if anchor_at is None or anchor_id is None:
                    raise RuntimeError("Chat image root source lost its actual continuation anchor")
                continuation = self.cursor_codec.encode_roots(
                    scope,
                    account_id,
                    digest,
                    OperatorChatImageUploadRootPosition(
                        anchor_at, anchor_id, visible[-1].created_at, visible[-1].id
                    ),
                )
            observed = await transaction.now()
            await audit_chat_image_account(transaction, principal, account_id, found=True)
            return OperatorChatImageUploadsPage(
                account_id, visible, continuation, anchor_at, anchor_id, observed
            )


@dataclass(frozen=True, slots=True)
class ReadOperatorChatImageHistory:
    unit_of_work: OperatorChatImageUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorChatImageCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        image_id: UUID,
        cursor: str | None = None,
    ) -> OperatorChatImageHistoryPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.chat_image_account(account_id)
            if actual is None:
                await audit_chat_image_account(transaction, principal, account_id, found=False)
                return None
            if actual != account_id:
                raise RuntimeError(
                    "Chat image history account source belongs to another requested account"
                )
            head = await transaction.chat_image_history_head(account_id, image_id)
            if head is None:
                # The real parent ACCOUNT was inspected even when its requested child is absent.
                await audit_chat_image_account(transaction, principal, account_id, found=True)
                return None
            if head.upload.id != image_id or head.upload.account_id != account_id:
                raise RuntimeError(
                    "Chat image history head belongs to another actual owner or image"
                )
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode_history(scope, account_id, image_id, cursor)
                if cursor is not None
                else None
            )
            if position is not None and position.anchor_version > head.latest_version:
                raise InvalidOperatorCursorError
            anchor = position.anchor_version if position is not None else head.latest_version
            window = OperatorChatImageHistoryWindow(
                anchor, position.before_version if position is not None else None
            )
            rows = await transaction.chat_image_history_revisions(account_id, image_id, window)
            validate_chat_image_revisions(rows, head.upload, window)
            visible = rows[:OPERATOR_CHAT_IMAGE_PAGE_SIZE]
            continuation = (
                self.cursor_codec.encode_history(
                    scope,
                    account_id,
                    image_id,
                    OperatorChatImageHistoryPosition(anchor, visible[-1].version),
                )
                if len(rows) > OPERATOR_CHAT_IMAGE_PAGE_SIZE
                else None
            )
            attempts = await transaction.chat_image_attempts_current(account_id, image_id)
            operation = await transaction.chat_image_matching_operation(account_id, image_id)
            validate_chat_image_metadata(attempts, operation, head.upload)
            observed = await transaction.now()
            await audit_chat_image_account(transaction, principal, account_id, found=True)
            return OperatorChatImageHistoryPage(
                head.upload, visible, continuation, anchor, observed, attempts, operation
            )


def validate_chat_image_revisions(
    rows: tuple[OperatorChatImageUploadRevision, ...],
    upload: OperatorChatImageUploadRoot,
    window: OperatorChatImageHistoryWindow,
) -> None:
    if len(rows) > OPERATOR_CHAT_IMAGE_PAGE_SIZE + 1:
        raise RuntimeError("Chat image revision source exceeded its bounded history page")
    previous = (
        window.before_version if window.before_version is not None else window.anchor_version + 1
    )
    for row in rows:
        if (
            (row.account_id, row.image_id, row.conversation_id, row.client_message_id)
            != (upload.account_id, upload.id, upload.conversation_id, upload.client_message_id)
            or row.version > window.anchor_version
            or row.version >= previous
        ):
            raise RuntimeError(
                "Chat image history source violates actual owner, chat image or version ordering"
            )
        previous = row.version


def validate_chat_image_metadata(
    attempts: tuple[OperatorChatImageAttempt, ...],
    operation: OperatorChatImageMatchingOperation | None,
    upload: OperatorChatImageUploadRoot,
) -> None:
    if (
        len(attempts) > MAX_OPERATOR_CHAT_IMAGE_ATTEMPTS
        or len({row.id for row in attempts}) != len(attempts)
        or tuple(row.number for row in attempts) != tuple(sorted({row.number for row in attempts}))
        or any(row.image_id != upload.id for row in attempts)
    ):
        raise RuntimeError("Chat image attempts violate their bounded actual preparation source")
    if operation is not None and (
        operation.author_id,
        operation.conversation_id,
        operation.client_message_id,
    ) != (upload.account_id, upload.conversation_id, upload.client_message_id):
        raise RuntimeError("Chat image operation differs from its actual client message scope")
