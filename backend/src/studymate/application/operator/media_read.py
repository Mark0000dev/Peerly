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
from studymate.application.operator.media_ports import (
    OperatorProfileMediaAudit,
    OperatorProfileMediaTransaction,
    OperatorProfileMediaUnitOfWork,
)
from studymate.domain.media import MAX_PHOTO_BYTES
from studymate.domain.operator.audit import OperatorAuditOutcome
from studymate.domain.operator.profile_media import (
    OperatorProfileMediaBytes,
    OperatorProfileMediaRequest,
    OperatorProfileMediaSource,
)

# Matches the existing bounded S3 reader; no retry or fallback storage path.
OPERATOR_MEDIA_READ_SECONDS = 20


async def source_for(
    transaction: OperatorProfileMediaTransaction,
    request: OperatorProfileMediaRequest,
) -> OperatorProfileMediaSource | None:
    source = await transaction.profile_media_source(request)
    if source is not None and not source.matches(request):
        raise RuntimeError(
            "Operator media source differs from the actual requested owner/upload/attempt"
        )
    return source


async def audit_media(
    transaction: OperatorProfileMediaTransaction,
    principal: OperatorPrincipal,
    request: OperatorProfileMediaRequest,
    source: OperatorProfileMediaSource | None,
    *,
    found: bool,
) -> None:
    await transaction.save_profile_media_audit(
        OperatorProfileMediaAudit(
            uuid4(),
            principal.access,
            request,
            await transaction.now(),
            OperatorAuditOutcome.READ if found else OperatorAuditOutcome.NOT_FOUND,
            source.upload_id if source is not None else None,
        )
    )
    await finish_operator(transaction, principal)


@dataclass(frozen=True, slots=True)
class ReadOperatorProfileMedia:
    unit_of_work: OperatorProfileMediaUnitOfWork
    hasher: SessionHasher
    storage: MediaReader

    async def __call__(
        self,
        credential: SessionCredential,
        request: OperatorProfileMediaRequest,
    ) -> OperatorProfileMediaBytes | None:
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
        return OperatorProfileMediaBytes(request.kind, data) if data is not None else None

    async def _read_object(self, request: OperatorProfileMediaRequest) -> bytes | None:
        try:
            async with asyncio.timeout(OPERATOR_MEDIA_READ_SECONDS):
                data = await self.storage.read(request.reference)
        except MediaObjectMissingError:
            return None
        except (MediaStorageUnavailableError, InvalidImageError, TimeoutError) as error:
            raise StorageUnavailableError from error
        if not data or len(data) > MAX_PHOTO_BYTES:
            raise StorageUnavailableError
        return data
