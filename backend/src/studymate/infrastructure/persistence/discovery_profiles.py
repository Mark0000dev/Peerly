from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from studymate.application.discovery.profiles import (
    DiscoveryProfileSource,
)
from studymate.application.identity.sessions import IdentitySnapshot
from studymate.application.safety.blocks import OwnBlockResult
from studymate.domain.identity import StudentEmail
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.domain.membership import Membership
from studymate.domain.relationships import AccountPair
from studymate.domain.reports import ProfileAccessContext
from studymate.infrastructure.observability.tracing import (
    current_origin,
    record_peer_profile_resource,
)
from studymate.infrastructure.persistence.block_models import (
    BlockRecord,
    BlockRevisionRecord,
    RelationshipRecord,
)
from studymate.infrastructure.persistence.block_state import read_own_block
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityTransaction
from studymate.infrastructure.persistence.media_models import (
    PhotoRecord,
    PhotoRevisionRecord,
    PhotoUploadRevisionRecord,
)
from studymate.infrastructure.persistence.onboarding import read_setup_snapshot
from studymate.infrastructure.persistence.registration_models import RegistrationReceiptRecord
from studymate.infrastructure.persistence.report_models import ProfileAccessRecord
from studymate.infrastructure.persistence.transactions import open_transaction


@dataclass(frozen=True, slots=True)
class SqlDiscoveryProfileReader(SqlIdentityTransaction):
    async def profile_source(self, account_id: UUID) -> DiscoveryProfileSource | None:
        account = await self.session.get(AccountRecord, account_id)
        if account is None:
            return None
        binding = await self.session.get(InstitutionalBindingRecord, account_id)
        registered = await self.session.scalar(
            select(RegistrationReceiptRecord.id).where(
                RegistrationReceiptRecord.account_id == account_id
            )
        )
        return DiscoveryProfileSource(
            await read_setup_snapshot(self.session, account_id),
            Membership(StudentEmail(binding.email), binding.verified_at, binding.revoked_at)
            if binding is not None
            else None,
            registered is not None,
            account.banned_at is not None,
            account.deleted_at is not None,
        )

    async def pair_blocked(self, actor_id: UUID, target_id: UUID) -> bool:
        pair = AccountPair.between(actor_id, target_id)
        selected = (
            select(BlockRevisionRecord.relationship_id)
            .join(
                BlockRecord,
                (BlockRecord.relationship_id == BlockRevisionRecord.relationship_id)
                & (BlockRecord.blocker_id == BlockRevisionRecord.blocker_id)
                & (BlockRecord.current_version == BlockRevisionRecord.version),
            )
            .join(RelationshipRecord, RelationshipRecord.id == BlockRecord.relationship_id)
            .where(
                RelationshipRecord.low_id == pair.low,
                RelationshipRecord.high_id == pair.high,
                BlockRevisionRecord.blocked.is_(True),
            )
        )
        return bool(await self.session.scalar(select(selected.exists())))

    async def display_reference(
        self, account_id: UUID, photo_version: int
    ) -> MediaObjectRef | None:
        row = (
            await self.session.execute(
                select(PhotoRevisionRecord.upload_id, PhotoUploadRevisionRecord.attempt_id)
                .join(
                    PhotoRecord,
                    (PhotoRecord.account_id == PhotoRevisionRecord.account_id)
                    & (PhotoRecord.current_version == PhotoRevisionRecord.version),
                )
                .join(
                    PhotoUploadRevisionRecord,
                    (PhotoUploadRevisionRecord.account_id == PhotoRevisionRecord.account_id)
                    & (PhotoUploadRevisionRecord.upload_id == PhotoRevisionRecord.upload_id)
                    & (PhotoUploadRevisionRecord.version == PhotoRevisionRecord.upload_version),
                )
                .where(
                    PhotoRevisionRecord.account_id == account_id,
                    PhotoRevisionRecord.version == photo_version,
                    PhotoUploadRevisionRecord.state == "ready",
                )
            )
        ).one_or_none()
        if row is None:
            return None
        upload_id, attempt_id = row
        if attempt_id is None:
            return None
        record_peer_profile_resource(account_id, photo_version)
        return MediaObjectRef(upload_id, MediaObjectKind.DISPLAY, attempt_id)

    async def own_block_state(self, actor_id: UUID, target_id: UUID) -> OwnBlockResult:
        snapshot = await read_own_block(self.session, actor_id, target_id)
        current = snapshot.own
        return (
            OwnBlockResult(target_id, current.blocked, current.version, current.changed_at)
            if current is not None
            else OwnBlockResult(target_id, False, 0, None)
        )

    async def remember_profile_access(self, context: ProfileAccessContext) -> None:
        snapshot = context.snapshot
        origin = current_origin()
        self.session.add(
            ProfileAccessRecord(
                id=context.id,
                viewer_id=context.viewer_id,
                target_id=snapshot.account_id,
                profile_version=snapshot.profile_version,
                photo_version=snapshot.photo_version,
                goal_id=snapshot.goal_id,
                goal_version=snapshot.goal_version,
                help_version=snapshot.help_version,
                issued_at=context.issued_at,
                request_id=origin.request_id if origin is not None else None,
                action_id=origin.action_id if origin is not None else None,
                trace_id=origin.trace_id if origin is not None else None,
                span_id=origin.span_id if origin is not None else None,
            )
        )
        await self.session.flush()
        record_peer_profile_resource(snapshot.account_id, snapshot.photo_version, context.id)


@dataclass(frozen=True, slots=True)
class SqlDiscoveryProfileTransaction(SqlDiscoveryProfileReader):
    peer_id: UUID

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        return await self.lock_identity_for_peer(secret_digest, self.peer_id)


@dataclass(frozen=True, slots=True)
class SqlDiscoveryProfileUnitOfWork:
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def transaction(self, target_id: UUID) -> AsyncIterator[SqlDiscoveryProfileTransaction]:
        async with open_transaction(self.sessions) as session:
            yield SqlDiscoveryProfileTransaction(session, target_id)
