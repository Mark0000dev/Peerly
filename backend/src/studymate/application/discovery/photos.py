from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from studymate.application.discovery.profiles import (
    DiscoveryProfileReader,
    DiscoveryProfileUnavailableError,
    authorize_discovery_profile,
)
from studymate.application.identity.sessions import (
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
)
from studymate.application.media.storage import MediaReader
from studymate.domain.media import MediaObjectKind, MediaObjectRef


class DiscoveryPhotoTransaction(DiscoveryProfileReader, Protocol):
    async def display_reference(
        self, account_id: UUID, photo_version: int
    ) -> MediaObjectRef | None: ...


class DiscoveryPhotoUnitOfWork(Protocol):
    def transaction(
        self, target_id: UUID
    ) -> AbstractAsyncContextManager[DiscoveryPhotoTransaction]: ...


@dataclass(frozen=True, slots=True)
class ReadDiscoveryPhoto:
    unit_of_work: DiscoveryPhotoUnitOfWork
    hasher: SessionHasher
    storage: MediaReader

    async def _authorized_reference(
        self,
        transaction: DiscoveryPhotoTransaction,
        credential: SessionCredential,
        target_id: UUID,
        photo_version: int,
    ) -> MediaObjectRef:
        actor, target = await authorize_discovery_profile(
            transaction, credential, self.hasher, target_id
        )
        photo = target.setup.photo
        if photo is None or photo.version != photo_version:
            raise DiscoveryProfileUnavailableError
        reference = await transaction.display_reference(target_id, photo_version)
        if reference is None:
            raise DiscoveryProfileUnavailableError
        if reference.kind != MediaObjectKind.DISPLAY or reference.upload_id != photo.upload_id:
            raise RuntimeError("Peer photo reference disagrees with its authorised revision")
        if not actor.session.is_active(await transaction.now()):
            raise UnauthenticatedError
        return reference

    async def __call__(
        self, credential: SessionCredential, target_id: UUID, photo_version: int
    ) -> bytes:
        if isinstance(photo_version, bool) or photo_version < 1:
            raise ValueError("Peer photo revision must be positive")
        async with self.unit_of_work.transaction(target_id) as transaction:
            reference = await self._authorized_reference(
                transaction, credential, target_id, photo_version
            )
        data = await self.storage.read(reference)
        # No SQL connection or permission lock is held during storage I/O. Recheck
        # current lifecycle, pair and photo after that wait, before releasing bytes.
        async with self.unit_of_work.transaction(target_id) as transaction:
            current = await self._authorized_reference(
                transaction, credential, target_id, photo_version
            )
            if current != reference:
                raise DiscoveryProfileUnavailableError
        return data
