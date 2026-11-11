"""Bounded privileged retained-object read, with final authority/audit before bytes escape."""

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from studymate.application.errors import StorageUnavailableError
from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
)
from studymate.application.media.processing import InvalidImageError
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaReader,
    MediaStorageUnavailableError,
)
from studymate.application.operator.authority import (
    OperatorAccessDeniedError,
    OperatorPrincipal,
    finish_operator,
    require_operator,
)
from studymate.application.operator.chat_media_ports import (
    OperatorChatMediaAudit,
    OperatorChatMediaTransaction,
    OperatorChatMediaUnitOfWork,
)
from studymate.domain.media import MAX_PHOTO_BYTES
from studymate.domain.operator.audit import OperatorAuditOutcome
from studymate.domain.operator.chat_media import (
    OperatorChatMediaBytes,
    OperatorChatMediaRequest,
    OperatorChatMediaSource,
)

# Matches the existing bounded S3 reader; no retry or fallback storage path.
OPERATOR_CHAT_MEDIA_READ_SECONDS = 20


async def source_for(
    transaction: OperatorChatMediaTransaction,
    request: OperatorChatMediaRequest,
) -> OperatorChatMediaSource | None:
    source = await transaction.chat_media_source(request)
    if source is not None and not source.matches(request):
        raise RuntimeError(
            "Operator media source differs from the actual requested owner/image/attempt"
        )
    return source


async def audit_media(
    transaction: OperatorChatMediaTransaction,
    principal: OperatorPrincipal,
    request: OperatorChatMediaRequest,
    source: OperatorChatMediaSource | None,
    *,
    found: bool,
) -> None:
    await transaction.save_chat_media_audit(
        OperatorChatMediaAudit(
            uuid4(),
            principal.access,
            request,
            await transaction.now(),
            OperatorAuditOutcome.READ if found else OperatorAuditOutcome.NOT_FOUND,
            source.image_id if source is not None else None,
        )
    )
    await finish_operator(transaction, principal)


@dataclass(frozen=True, slots=True)
class ReadOperatorChatMedia:
    unit_of_work: OperatorChatMediaUnitOfWork
    hasher: SessionHasher
    storage: MediaReader

    async def __call__(
        self,
        credential: SessionCredential,
        request: OperatorChatMediaRequest,
    ) -> OperatorChatMediaBytes | None:
        async with self.unit_of_work.transaction() as transaction:
            initial = await require_operator(transaction, credential, self.hasher)
            source = await source_for(transaction, request)
            if source is None:
                await audit_media(transaction, initial, request, None, found=False)
                return None
            await finish_operator(transaction, initial)
        # No SQL transaction or operator/source lock survives into object I/O.
        data = await self._read_object(request)
        async with self.unit_of_work.transaction() as transaction:
            final = await require_operator(transaction, credential, self.hasher)
            if (
                final.identity.session.id != initial.identity.session.id
                or final.identity.session.account_id != initial.identity.session.account_id
            ):
                raise UnauthenticatedError
            if final.access != initial.access:
                raise OperatorAccessDeniedError
            current = await source_for(transaction, request)
            if current is None:
                await audit_media(transaction, final, request, None, found=False)
                return None
            await audit_media(transaction, final, request, current, found=data is not None)
        return OperatorChatMediaBytes(request.kind, data) if data is not None else None

    async def _read_object(self, request: OperatorChatMediaRequest) -> bytes | None:
        try:
            async with asyncio.timeout(OPERATOR_CHAT_MEDIA_READ_SECONDS):
                data = await self.storage.read(request.reference)
        except MediaObjectMissingError:
            return None
        except (MediaStorageUnavailableError, InvalidImageError, TimeoutError) as error:
            raise StorageUnavailableError from error
        if not data or len(data) > MAX_PHOTO_BYTES:
            raise StorageUnavailableError
        return data
