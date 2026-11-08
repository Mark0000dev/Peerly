from uuid import UUID, uuid4

import pytest

from studymate.domain.operator.audit import OperatorAction
from studymate.domain.operator.timeline import OperatorEventKind
from studymate.infrastructure.operator.models import (
    OperatorAccessRevisionRecord,
    OperatorAuditRecord,
)
from studymate.infrastructure.operator.timeline_values import audit_value, event_value
from studymate.infrastructure.persistence.product_event_models import ProductEventRecord
from studymate.presentation.operator.timeline_models import audit_response, event_response
from tests.unit.identity_store import NOW


def row_for(kind: OperatorEventKind) -> ProductEventRecord:
    row = ProductEventRecord(
        id=uuid4(),
        account_id=uuid4(),
        kind=kind.value,
        schema_version=1,
        occurrence_key="synthetic",
        occurred_at=NOW,
    )
    profile_fields(row, kind)
    contact_fields(row, kind)
    journal_fields(row, kind)
    return row


def profile_fields(row: ProductEventRecord, kind: OperatorEventKind) -> None:
    if kind in {OperatorEventKind.GOAL_SAVED, OperatorEventKind.GOAL_COMPLETED}:
        row.goal_id, row.goal_version, row.subject_id = uuid4(), 1, uuid4()
        row.topic_present, row.shared_learning = True, False
    elif kind == OperatorEventKind.PROFILE_SAVED:
        row.profile_version = 1
    elif kind == OperatorEventKind.HELP_SAVED:
        row.help_version = 1
    elif kind == OperatorEventKind.PHOTO_PUBLISHED:
        row.photo_version = 1
    elif kind == OperatorEventKind.PROFILE_READY:
        row.profile_version, row.onboarding_task = 1, "find_help"
    elif kind in {
        OperatorEventKind.PROFILE_HIDDEN,
        OperatorEventKind.PROFILE_RESTORED,
        OperatorEventKind.EXPOSURE_CONFIRMED,
    }:
        row.visibility_version = 1
    elif kind == OperatorEventKind.AI_COMPLETED:
        row.ai_job_id, row.ai_kind, row.ai_state, row.ai_reason = (
            uuid4(),
            "clarify_goal",
            "failed",
            "auth_unavailable",
        )
    elif kind == OperatorEventKind.REPORT_CREATED:
        row.report_id = uuid4()
    elif kind == OperatorEventKind.BLOCK_CHANGED:
        row.block_relationship_id, row.block_version, row.blocked = uuid4(), 1, True
    elif kind == OperatorEventKind.DECK_DECISION_CHANGED:
        row.private_pass_id, row.private_pass_version, row.private_passed = uuid4(), 1, False


def contact_fields(row: ProductEventRecord, kind: OperatorEventKind) -> None:
    if kind == OperatorEventKind.REQUEST_CHANGED:
        row.connection_request_id, row.connection_request_version = uuid4(), 1
        row.connection_request_recipient_id, row.connection_request_state = uuid4(), "pending"
        row.request_initiator_id = row.connection_request_recipient_id
    elif kind == OperatorEventKind.REQUEST_VIEWED:
        row.request_view_ack_id = uuid4()
    elif kind in {OperatorEventKind.MESSAGE_CONFIRMED, OperatorEventKind.MESSAGE_CANCELLED}:
        row.message_operation_id = uuid4()
        row.message_operation_state = (
            "confirmed" if kind == OperatorEventKind.MESSAGE_CONFIRMED else "cancelled"
        )
    elif kind == OperatorEventKind.CONVERSATION_READ:
        row.conversation_read_id, row.read_conversation_id = uuid4(), uuid4()
    elif kind == OperatorEventKind.GOAL_SHARED:
        row.goal_share_id, row.goal_share_context_version, row.goal_share_conversation_id = (
            uuid4(),
            1,
            uuid4(),
        )


def journal_fields(row: ProductEventRecord, kind: OperatorEventKind) -> None:
    if kind == OperatorEventKind.ACCOUNT_LIFECYCLE_CHANGED:
        row.lifecycle_revision_id, row.lifecycle_account_id = uuid4(), uuid4()
        row.lifecycle_version, row.lifecycle_operation = 1, "ban"
    elif kind == OperatorEventKind.OPERATOR_INSPECTED:
        row.operator_audit_id, row.operator_access_version, row.operator_action = (
            uuid4(),
            1,
            "read_account",
        )
    elif kind == OperatorEventKind.STUDY_REPORTED:
        row.study_outcome_id, row.study_outcome_version = uuid4(), 1
        row.study_conversation_id, row.study_answer = uuid4(), "yes"
    elif kind == OperatorEventKind.FEEDBACK_SAVED:
        row.peer_feedback_id, row.peer_feedback_version, row.feedback_again = uuid4(), 1, "maybe"
    elif kind == OperatorEventKind.STUDY_PROMPT:
        row.study_prompt_id, row.study_prompt_conversation_id = uuid4(), uuid4()


@pytest.mark.parametrize("kind", list(OperatorEventKind))
def test_actual_canonical_columns_map_to_closed_metadata_not_private_source_content(
    kind: OperatorEventKind,
) -> None:
    row = row_for(kind)
    actual = event_value(row)
    dto = event_response(actual)
    assert dto.id == row.id
    assert dto.subject_account_id == row.account_id
    assert dto.kind == kind
    assert dto.schema_version == row.schema_version
    assert actual.sources[0].owner_id == row.account_id
    for field in ("goal_text", "message_body", "team_note", "ai_input", "result", "secret_digest"):
        assert field not in type(dto).model_fields


@pytest.mark.parametrize("action", list(OperatorAction))
def test_all_actual_audit_actions_preserve_original_active_grant_and_hide_query_fingerprint(
    action: OperatorAction,
) -> None:
    actor_id = uuid4()
    grant = OperatorAccessRevisionRecord(
        account_id=actor_id, version=1, active=True, changed_at=NOW
    )
    searching = action in {
        OperatorAction.SEARCH_ACCOUNTS,
        OperatorAction.SEARCH_EVENTS,
        OperatorAction.SEARCH_REPORTS,
    }
    resource = {
        OperatorAction.SEARCH_ACCOUNTS: "account",
        OperatorAction.READ_ACCOUNT: "account",
        OperatorAction.READ_CONVERSATION_MESSAGES: "conversation",
        OperatorAction.SEARCH_EVENTS: "event",
        OperatorAction.READ_EVENT: "event",
        OperatorAction.READ_AUDIT: "audit",
        OperatorAction.SEARCH_REPORTS: "report",
        OperatorAction.READ_REPORT: "report",
        OperatorAction.READ_MEDIA: "profile_media",
    }[action]
    requested = None if searching else uuid4()
    returned: list[UUID] = (
        []
        if requested is None or action == OperatorAction.READ_CONVERSATION_MESSAGES
        else [requested]
    )
    row = OperatorAuditRecord(
        id=uuid4(),
        operator_id=actor_id,
        operator_access_version=1,
        operator_access_active=True,
        action=action.value,
        resource_kind=resource,
        requested_id=requested,
        result_ids=returned,
        outcome="search" if searching else "read",
        occurred_at=NOW,
        query_fingerprint=b"h" * 32 if searching else None,
    )
    if action == OperatorAction.READ_MEDIA:
        row.requested_media_owner_id = uuid4()
        row.requested_media_attempt_id = uuid4()
        row.requested_media_kind = "original"
        row.actual_source_upload_id = requested
    actual = audit_value(row, grant)
    dto = audit_response(actual)
    assert dto.operator_id == actor_id
    assert dto.operator_access_changed_at == grant.changed_at
    assert dto.action == action
    assert dto.query_fingerprinted == searching
    assert "query_fingerprint" not in type(dto).model_fields


@pytest.mark.parametrize("fault", ["missing_source", "wrong_grant"])
def test_broken_actual_source_mapping_does_not_fabricate_references(fault: str) -> None:
    with pytest.raises(RuntimeError, match=r"actual stored source|actual historical"):
        invalid_mapping(fault)


def invalid_mapping(fault: str) -> None:
    if fault == "missing_source":
        row = row_for(OperatorEventKind.GOAL_SAVED)
        row.goal_id = None
        event_value(row)
    else:
        grant = OperatorAccessRevisionRecord(
            account_id=uuid4(), version=1, active=True, changed_at=NOW
        )
        audit = OperatorAuditRecord(
            operator_id=uuid4(),
            operator_access_version=1,
            operator_access_active=True,
            action="read_account",
            resource_kind="account",
            occurred_at=NOW,
            result_ids=[],
        )
        audit_value(audit, grant)


@pytest.mark.parametrize("operation", ["ban", "unban", "delete"])
def test_lifecycle_projection_retains_actor_target_and_exact_source_without_reason(
    operation: str,
) -> None:
    row = row_for(OperatorEventKind.ACCOUNT_LIFECYCLE_CHANGED)
    row.lifecycle_operation = operation
    if operation == "delete":
        row.lifecycle_account_id = row.account_id
    actual = event_value(row)
    source = actual.sources[0]
    assert source.id == row.lifecycle_revision_id
    assert source.owner_id == row.account_id
    assert source.related_account_id == row.lifecycle_account_id
    assert source.version == row.lifecycle_version
    assert actual.facts.lifecycle_operation == operation
    response = event_response(actual).model_dump(mode="json")
    assert "reason" not in response
    assert "reason" not in event_response(actual).facts.model_fields_set
    assert response["subject_account_id"] == str(row.account_id)
