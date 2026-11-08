from dataclasses import replace

from studymate.application.requests.peers import request_peer
from studymate.domain.requests.projections import RequestPeerState
from tests.unit.requests.store import PEER, SENDER, Store


def test_only_current_public_guard_allows_name_photo() -> None:
    store = Store()
    own, target = store.sources[SENDER], store.sources[PEER]
    public = request_peer(own, target, blocked=False)
    assert public.state == RequestPeerState.PUBLIC
    assert public.display_name is not None
    assert public.photo_version is not None
    assert public.display_name not in repr(public)
    for first, second, blocked in (
        (None, target, False),
        (own, None, False),
        (own, target, True),
        (replace(own, banned=True), target, False),
        (own, replace(target, banned=True), False),
        (own, replace(target, registered=False), False),
    ):
        masked = request_peer(first, second, blocked=blocked)
        assert masked.state == RequestPeerState.UNAVAILABLE
        assert masked.display_name is None
        assert masked.photo_version is None
    deleted = request_peer(own, replace(target, deleted=True), blocked=True)
    assert deleted.state == RequestPeerState.DELETED
    assert deleted.display_name is None
    assert deleted.photo_version is None
