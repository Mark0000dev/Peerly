from uuid import UUID

from studymate.application.discovery.profiles import DiscoveryProfileSource
from studymate.application.identity.sessions import IdentitySnapshot, StudentActionDeniedError
from studymate.application.requests.ports import RequestPreview, RequestTransaction
from studymate.application.requests.preview_checks import PreviewBlockReason
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.requests.context import GoalSnapshot, HelpSnapshot, RequestContext
from studymate.domain.requests.states import RequestUnavailableError


def context(
    mode: DiscoveryMode, sender: DiscoveryProfileSource, recipient: DiscoveryProfileSource
) -> RequestContext:
    def goal(source: DiscoveryProfileSource) -> GoalSnapshot | None:
        saved = source.setup.goal
        return GoalSnapshot(saved.goal, saved.subject_label) if saved is not None else None

    def help_snapshot(source: DiscoveryProfileSource) -> HelpSnapshot | None:
        saved = source.setup.help_subjects
        return HelpSnapshot(saved.revision, saved.labels) if saved is not None else None

    try:
        return RequestContext(
            sender.setup.account_id,
            recipient.setup.account_id,
            mode,
            sender_goal=goal(sender) if mode != DiscoveryMode.OFFER_HELP else None,
            recipient_goal=goal(recipient) if mode != DiscoveryMode.FIND_HELP else None,
            sender_help=help_snapshot(sender) if mode == DiscoveryMode.OFFER_HELP else None,
            recipient_help=help_snapshot(recipient) if mode == DiscoveryMode.FIND_HELP else None,
        )
    except ValueError:
        raise RequestUnavailableError from None


async def eligible_sources(
    transaction: RequestTransaction, actor: IdentitySnapshot, peer_id: UUID
) -> tuple[DiscoveryProfileSource, DiscoveryProfileSource]:
    actor_id = actor.session.account_id
    own = await transaction.profile_source(actor_id)
    if own is None or not own.can_make_new_contacts:
        raise StudentActionDeniedError
    peer = await transaction.profile_source(peer_id)
    if actor_id == peer_id or peer is None or not peer.can_make_new_contacts:
        raise RequestUnavailableError
    if own.setup.account_id != actor_id or peer.setup.account_id != peer_id:
        raise RuntimeError("Request source belongs to another account")
    if await transaction.pair_blocked(actor_id, peer_id):
        raise RequestUnavailableError
    return own, peer


async def preview_source_reason(
    transaction: RequestTransaction,
    identity: IdentitySnapshot,
    peer_id: UUID,
    preview: RequestPreview,
) -> PreviewBlockReason | None:
    try:
        own, peer = await eligible_sources(transaction, identity, peer_id)
    except (StudentActionDeniedError, RequestUnavailableError):
        return PreviewBlockReason.UNAVAILABLE
    try:
        current = context(preview.context.mode, own, peer)
    except RequestUnavailableError:
        return PreviewBlockReason.SOURCE_CHANGED
    return PreviewBlockReason.SOURCE_CHANGED if current != preview.context else None
