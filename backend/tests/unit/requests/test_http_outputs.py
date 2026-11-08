from dataclasses import replace
from uuid import uuid4

from studymate.application.requests.ports import (
    AcceptedRequest,
    AlreadyConnected,
    ConversationReference,
    ExistingOutgoing,
    IncomingRequestExists,
    RequestPreview,
    SentRequest,
)
from studymate.application.requests.preview_checks import CheckedRequestPreview, RequestPreviewCheck
from studymate.domain.requests.context import HelpSnapshot
from studymate.domain.requests.limits import RequestLimits, SendQuota, send_day_bounds
from studymate.domain.requests.views import RequestViewReceipt
from studymate.domain.study_context import HelpSubject, HelpSubjects
from studymate.presentation.requests.outputs import (
    PreviewResponse,
    academic_context,
    accepted_response,
    mutation_response,
    preview_response,
    send_response,
    viewed_response,
)
from tests.unit.identity_store import NOW
from tests.unit.requests.store import PEER, SENDER
from tests.unit.requests.test_states import request


def test_public_context_only_discloses_relevant_help_not_all_declared_subjects() -> None:
    value = request()
    help_snapshot = value.context.recipient_help
    assert help_snapshot is not None
    original = help_snapshot.revision.subjects.values[0]
    retained = HelpSnapshot(
        replace(
            help_snapshot.revision,
            subjects=HelpSubjects((original, HelpSubject(uuid4(), "unrelated private note"))),
        ),
        (*help_snapshot.labels, "unrelated private label"),
    )
    context = academic_context(replace(value.context, recipient_help=retained))
    encoded = context.model_dump_json()
    assert "unrelated private" not in encoded
    assert context.recipient_help is not None
    assert context.recipient_help.version == retained.revision.version
    assert context.recipient_goal is None
    assert context.sender_help is None
    assert context.sender_goal is not None
    assert context.sender_goal.owner_id == SENDER
    assert context.recipient_help.owner_id == PEER


def test_recovery_receipts_never_claim_second_draft_sent_or_autoaccepted() -> None:
    value = request()
    assert send_response(SentRequest(value)).outcome == "sent"
    assert send_response(ExistingOutgoing(value)).outcome == "existing_outgoing"
    assert send_response(IncomingRequestExists(value)).outcome == "incoming"
    actual = ConversationReference(uuid4(), value.relationship_id, value.pair, value.id)
    connected = send_response(AlreadyConnected(actual))
    assert connected.outcome == "connected"
    assert connected.conversation_id == actual.id
    assert connected.request_id == actual.request_id
    accepted = AcceptedRequest(value.accept(PEER, actual.id, NOW), actual)
    assert accepted_response(accepted).conversation_id == actual.id
    preview = preview_response(
        CheckedRequestPreview(
            RequestPreview(value.preview_id, value.context, NOW),
            RequestPreviewCheck(
                value.preview_id,
                NOW,
                SendQuota(0, 0),
                RequestLimits(),
                send_day_bounds(NOW)[1],
                None,
                None,
            ),
        )
    )
    assert isinstance(preview, PreviewResponse)
    assert preview.preview_id == value.preview_id
    assert preview_response(IncomingRequestExists(value)).outcome == "incoming"


def test_original_mutation_receipt_does_not_add_current_capabilities_or_sender_undo() -> None:
    value = request().decline(PEER, NOW)
    own_action = mutation_response(value, "declined")
    assert own_action.version == value.version
    assert own_action.undo_until == value.decline_until
    sender_recovery = mutation_response(value, "existing_outgoing")
    assert sender_recovery.undo_until is None
    assert "capabilities" not in sender_recovery.model_dump()
    assert "text" not in sender_recovery.model_dump()
    assert "lease" not in sender_recovery.model_dump_json()
    receipt = RequestViewReceipt(uuid4(), PEER, value.id, value.version, uuid4(), NOW)
    mapped = viewed_response(receipt)
    assert mapped.disclosure_id == receipt.disclosure_id
    assert mapped.acknowledgement_id == receipt.id
    assert "viewer_id" not in mapped.model_dump()
