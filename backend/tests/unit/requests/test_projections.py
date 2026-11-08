from datetime import timedelta
from uuid import uuid4

import pytest

from studymate.domain.requests.projections import (
    RequestBox,
    RequestListView,
    RequestPublicState,
    RequestVisibility,
    in_request_view,
    observe_request,
)
from studymate.domain.requests.states import REQUEST_LIFETIME, UNDO_WINDOW, RequestUnavailableError
from studymate.domain.requests.views import RequestDisclosure, RequestViewReceipt
from tests.unit.identity_store import NOW
from tests.unit.requests.store import PEER, SENDER
from tests.unit.requests.test_states import request

VISIBLE = RequestVisibility(False, True, True)


def test_deadline_projection_preserves_actual_stored_revision() -> None:
    value = request().decline(PEER, NOW)
    sender = observe_request(value, SENDER, NOW, VISIBLE)
    recipient = observe_request(value, PEER, NOW, VISIBLE)
    assert sender.state == RequestPublicState.PENDING
    assert sender.undo_until is None
    assert sender.capabilities.can_withdraw
    assert recipient.state == RequestPublicState.PENDING_DECLINE
    assert recipient.undo_until == NOW + UNDO_WINDOW
    assert recipient.capabilities.can_undo_decline
    assert not recipient.capabilities.can_accept
    final = observe_request(value, PEER, NOW + UNDO_WINDOW, VISIBLE)
    assert final.version == value.version
    assert final.state == RequestPublicState.DECLINED
    assert final.undo_until is None
    assert not final.capabilities.can_undo_decline
    assert (
        observe_request(value, SENDER, NOW + UNDO_WINDOW, VISIBLE).state
        == RequestPublicState.CLOSED
    )


def test_unread_requires_incoming_pending_without_explicit_ack() -> None:
    value = request()
    assert observe_request(value, PEER, NOW, VISIBLE).unread
    assert not observe_request(value, SENDER, NOW, VISIBLE).unread
    acknowledged = RequestVisibility(True, True, True)
    assert not observe_request(value, PEER, NOW, acknowledged).unread
    expired = observe_request(value, PEER, NOW + REQUEST_LIFETIME, VISIBLE)
    assert expired.state == RequestPublicState.EXPIRED
    assert expired.version == value.version
    assert not expired.unread
    assert not expired.capabilities.can_accept
    assert not expired.capabilities.can_decline


def test_hidden_profile_retains_actual_accepted_conversation_only() -> None:
    accepted = request().accept(PEER, uuid4(), NOW)
    hidden = RequestVisibility(False, False, False)
    observed = observe_request(accepted, PEER, NOW, hidden)
    assert observed.capabilities.can_open_conversation
    assert not observed.capabilities.can_view_profile
    assert not observed.capabilities.can_accept
    pending = observe_request(request(), PEER, NOW, hidden)
    assert not pending.capabilities.can_accept
    assert pending.capabilities.can_decline
    with pytest.raises(RequestUnavailableError):
        observe_request(accepted, uuid4(), NOW, VISIBLE)


def test_withdrawal_and_unavailable_do_not_disclose_peer_reason() -> None:
    withdrawn = request().withdraw(SENDER, NOW)
    sender = observe_request(withdrawn, SENDER, NOW, VISIBLE)
    recipient = observe_request(withdrawn, PEER, NOW, VISIBLE)
    assert sender.box == RequestBox.SENT
    assert sender.state == RequestPublicState.WITHDRAWN
    assert sender.cooldown_until is not None
    assert recipient.state == RequestPublicState.CLOSED
    assert recipient.cooldown_until is None
    closed = request().close_unavailable(NOW)
    assert observe_request(closed, SENDER, NOW, VISIBLE).state == RequestPublicState.CLOSED
    assert observe_request(closed, PEER, NOW, VISIBLE).state == RequestPublicState.CLOSED


def test_recently_declined_selection_ends_at_server_deadline() -> None:
    value = request().decline(PEER, NOW)
    assert in_request_view(value, RequestListView.RECENTLY_DECLINED, NOW)
    assert in_request_view(value, RequestListView.ACTIVE, NOW)
    assert not in_request_view(value, RequestListView.HISTORY, NOW)
    at = NOW + UNDO_WINDOW
    assert not in_request_view(value, RequestListView.RECENTLY_DECLINED, at)
    assert not in_request_view(value, RequestListView.ACTIVE, at)
    assert in_request_view(value, RequestListView.HISTORY, at)
    accepted = request().accept(PEER, uuid4(), NOW)
    assert in_request_view(accepted, RequestListView.ACTIVE, at)


@pytest.mark.parametrize("version", [0, -1, True])
def test_disclosure_and_ack_require_actual_positive_source_revision(version: int) -> None:
    with pytest.raises(ValueError, match="stored request revision"):
        RequestDisclosure(uuid4(), PEER, uuid4(), version, NOW)
    with pytest.raises(ValueError, match="stored request revision"):
        RequestViewReceipt(uuid4(), PEER, uuid4(), version, uuid4(), NOW)


def test_receipt_retains_disclosure_reference_without_becoming_profile_grant() -> None:
    value = request()
    disclosure = RequestDisclosure(uuid4(), PEER, value.id, value.version, NOW)
    receipt = RequestViewReceipt(
        uuid4(), PEER, value.id, value.version, disclosure.id, NOW + timedelta(seconds=1)
    )
    assert receipt.disclosure_id == disclosure.id
    assert receipt.stored_version == disclosure.stored_version
