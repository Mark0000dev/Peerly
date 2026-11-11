from dataclasses import dataclass, field
from uuid import UUID, uuid4

from studymate.application.idempotency import IntentFingerprinter, IntentKey
from studymate.application.identity.sessions import (
    IdentitySnapshot,
    SessionCredential,
    SessionHasher,
    StudentActionDeniedError,
    UnauthenticatedError,
    require_verified_student,
)
from studymate.application.requests.intents import remember, replay
from studymate.application.requests.ports import (
    AlreadyConnected,
    ExistingOutgoing,
    IncomingRequestExists,
    PreviewResult,
    RequestCooldownError,
    RequestIntent,
    RequestPreview,
    RequestSourceChangedError,
    RequestTransaction,
    RequestUnitOfWork,
    SendResult,
    SentRequest,
)
from studymate.application.requests.preview_checks import (
    CheckedRequestPreview,
    PreviewBlockReason,
    RequestPreviewCheck,
    pair_block_reason,
)
from studymate.application.requests.sources import context, eligible_sources, preview_source_reason
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.relationships import AccountPair
from studymate.domain.requests.context import RequestText
from studymate.domain.requests.limits import RequestLimits, send_day_bounds
from studymate.domain.requests.states import ConnectionRequest, RequestUnavailableError


async def actor(
    transaction: RequestTransaction, credential: SessionCredential, hasher: SessionHasher
) -> IdentitySnapshot:
    identity, _ = await require_verified_student(transaction, await hasher.digest(credential))
    if not identity.activation_complete:
        raise StudentActionDeniedError
    return identity


async def finish(transaction: RequestTransaction, identity: IdentitySnapshot) -> None:
    if not identity.session.is_active(await transaction.now()):
        raise UnauthenticatedError


@dataclass(frozen=True, slots=True)
class PreviewRequest:
    unit_of_work: RequestUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(
        self, credential: SessionCredential, peer_id: UUID, mode: DiscoveryMode, key: IntentKey
    ) -> PreviewResult:
        async with self.unit_of_work.transaction(peer_id) as transaction:
            identity = await actor(transaction, credential, self.hasher)
            actor_id = identity.session.account_id
            digest = await self.fingerprinter.fingerprint(
                ("requests.preview.v1", str(actor_id), str(peer_id), mode.value)
            )
            prior = await replay(transaction, actor_id, "preview", key, digest)
            if prior is not None:
                if not isinstance(
                    prior,
                    (RequestPreview, ExistingOutgoing, IncomingRequestExists, AlreadyConnected),
                ):
                    raise RuntimeError("Stored preview intent has wrong result type")
                return prior
            now = await transaction.now()
            pair = await transaction.existing_pair(actor_id, peer_id, now)
            recovery: ExistingOutgoing | IncomingRequestExists | AlreadyConnected | None = None
            if pair is not None:
                if pair.pair != AccountPair.between(actor_id, peer_id):
                    raise RuntimeError("Request preview returned another pair")
                if pair.conversation is not None:
                    recovery = AlreadyConnected(pair.conversation)
                elif pair.pending is not None:
                    recovery = (
                        ExistingOutgoing(pair.pending)
                        if pair.pending.context.sender_id == actor_id
                        else IncomingRequestExists(pair.pending)
                    )
            if recovery is not None:
                await remember(
                    transaction, actor_id, "preview", key, RequestIntent(digest, recovery)
                )
                await finish(transaction, identity)
                return recovery
            own, peer = await eligible_sources(transaction, identity, peer_id)
            if (
                pair is not None
                and pair.sender_cooldown_until is not None
                and now < pair.sender_cooldown_until
            ):
                raise RequestCooldownError(pair.sender_cooldown_until)
            preview = RequestPreview(uuid4(), context(mode, own, peer), await transaction.now())
            await transaction.save_preview(preview)
            await remember(transaction, actor_id, "preview", key, RequestIntent(digest, preview))
            await finish(transaction, identity)
            return preview

    async def for_composer(
        self,
        credential: SessionCredential,
        peer_id: UUID,
        mode: DiscoveryMode,
        key: IntentKey,
        limits: RequestLimits,
    ) -> CheckedRequestPreview | ExistingOutgoing | IncomingRequestExists | AlreadyConnected:
        """Original retained intent, followed by an independent current advisory observation."""
        result = await self(credential, peer_id, mode, key)
        if not isinstance(result, RequestPreview):
            return result
        check = await self.check_current(credential, peer_id, result.id, limits)
        return CheckedRequestPreview(result, check)

    async def check_current(
        self,
        credential: SessionCredential,
        peer_id: UUID,
        preview_id: UUID,
        limits: RequestLimits,
    ) -> RequestPreviewCheck:
        """Recheck a retained draft without spending quota, settling state or writing intents."""
        async with self.unit_of_work.transaction(peer_id) as transaction:
            identity = await actor(transaction, credential, self.hasher)
            actor_id = identity.session.account_id
            preview = await transaction.preview(preview_id)
            if (
                preview is None
                or preview.context.sender_id != actor_id
                or preview.context.recipient_id != peer_id
            ):
                raise RequestUnavailableError
            now = await transaction.now()
            quota = await transaction.quota(actor_id, now)
            pair = await transaction.observe_pair(actor_id, peer_id, now)
            reason, cooldown = pair_block_reason(pair, actor_id, now, peer_id)
            if reason is None:
                reason = await preview_source_reason(transaction, identity, peer_id, preview)
            if reason is None:
                if quota.outgoing_pending >= limits.outgoing_pending:
                    reason = PreviewBlockReason.OUTGOING_PENDING_LIMIT
                elif quota.successful_today >= limits.successful_per_day:
                    reason = PreviewBlockReason.DAILY_SEND_LIMIT
            await finish(transaction, identity)
            return RequestPreviewCheck(
                preview_id, now, quota, limits, send_day_bounds(now)[1], reason, cooldown
            )


@dataclass(frozen=True, slots=True)
class SendRequest:
    unit_of_work: RequestUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    limits: RequestLimits = field(default_factory=RequestLimits)

    async def __call__(
        self,
        credential: SessionCredential,
        peer_id: UUID,
        preview_id: UUID,
        message: RequestText,
        key: IntentKey,
    ) -> SendResult:
        async with self.unit_of_work.transaction(peer_id) as transaction:
            identity = await actor(transaction, credential, self.hasher)
            actor_id = identity.session.account_id
            digest = await self.fingerprinter.fingerprint(
                (
                    "requests.send.v1",
                    str(actor_id),
                    str(peer_id),
                    str(preview_id),
                    message.text,
                    "none" if message.note is None else "note",
                    message.note or "",
                )
            )
            prior = await replay(transaction, actor_id, "send", key, digest)
            if prior is not None:
                if not isinstance(
                    prior, (SentRequest, ExistingOutgoing, IncomingRequestExists, AlreadyConnected)
                ):
                    raise RuntimeError("Stored send intent has wrong result type")
                return prior
            preview = await transaction.preview(preview_id)
            if (
                preview is None
                or preview.context.sender_id != actor_id
                or preview.context.recipient_id != peer_id
            ):
                raise RequestUnavailableError
            now = await transaction.now()
            pair = await transaction.pair_state(actor_id, peer_id, now)
            if pair.pair != AccountPair.between(actor_id, peer_id):
                raise RuntimeError("Request transaction returned another pair")
            result: SendResult
            if pair.conversation is not None:
                result = AlreadyConnected(pair.conversation)
            else:
                own, peer = await eligible_sources(transaction, identity, peer_id)
                if pair.pending is not None:
                    result = (
                        ExistingOutgoing(pair.pending)
                        if pair.pending.context.sender_id == actor_id
                        else IncomingRequestExists(pair.pending)
                    )
                else:
                    if pair.sender_cooldown_until is not None and now < pair.sender_cooldown_until:
                        raise RequestCooldownError(pair.sender_cooldown_until)
                    try:
                        current_context = context(preview.context.mode, own, peer)
                    except RequestUnavailableError:
                        raise RequestSourceChangedError from None
                    if current_context != preview.context:
                        raise RequestSourceChangedError
                    (await transaction.quota(actor_id, now)).check(self.limits)
                    request = ConnectionRequest(
                        uuid4(),
                        pair.relationship_id,
                        preview.id,
                        preview.context,
                        message,
                        now,
                        now,
                    )
                    await transaction.save_request(request)
                    result = SentRequest(request)
            await remember(transaction, actor_id, "send", key, RequestIntent(digest, result))
            await finish(transaction, identity)
            return result
