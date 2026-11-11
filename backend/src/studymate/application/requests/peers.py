"""Current public identity only; retained request content is not a profile grant."""

from studymate.application.discovery.profiles import DiscoveryProfileSource
from studymate.domain.requests.projections import RequestPeer, RequestPeerState


def request_peer(
    own: DiscoveryProfileSource | None,
    target: DiscoveryProfileSource | None,
    *,
    blocked: bool,
) -> RequestPeer:
    if target is not None and target.deleted:
        return RequestPeer(RequestPeerState.DELETED)
    if (
        own is None
        or target is None
        or blocked
        or not own.can_make_new_contacts
        or not target.can_make_new_contacts
    ):
        return RequestPeer(RequestPeerState.UNAVAILABLE)
    profile, photo = target.setup.profile, target.setup.photo
    if profile is None or photo is None or profile.basics.display_name is None:
        return RequestPeer(RequestPeerState.UNAVAILABLE)
    return RequestPeer(RequestPeerState.PUBLIC, profile.basics.display_name.value, photo.version)
