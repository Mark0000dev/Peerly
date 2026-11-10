from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from studymate.domain.operator.access import OperatorAccess
from studymate.domain.operator.profile_media import OperatorProfileMediaRequest
from studymate.domain.time import require_aware

OPERATOR_ACCOUNT_PAGE_SIZE = 20
OPERATOR_MESSAGE_PAGE_SIZE = 50
OPERATOR_EVENT_PAGE_SIZE = 50
FINGERPRINT_BYTES = 32


class OperatorAction(StrEnum):
    SEARCH_ACCOUNTS = "search_accounts"
    SEARCH_EVENTS = "search_events"
    SEARCH_REPORTS = "search_reports"
    SEARCH_SUPPORT_CASES = "search_support_cases"
    READ_SUPPORT_CASE = "read_support_case"
    READ_REPORT = "read_report"
    READ_MEDIA = "read_media"
    READ_EVENT = "read_event"
    READ_AUDIT = "read_audit"
    READ_ACCOUNT = "read_account"
    READ_CONVERSATION_MESSAGES = "read_conversation_messages"


class OperatorResourceKind(StrEnum):
    ACCOUNT = "account"
    CONVERSATION = "conversation"
    MESSAGE = "message"
    EVENT = "event"
    AUDIT = "audit"
    REPORT = "report"
    PROFILE_MEDIA = "profile_media"
    SUPPORT_CASE = "support_case"


class OperatorAuditOutcome(StrEnum):
    SEARCH = "search"
    READ = "read"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class OperatorResourceRef:
    kind: OperatorResourceKind
    id: UUID


@dataclass(frozen=True, slots=True)
class OperatorAudit:
    """Technical inspection/source fact, never human-view/consent or content capture."""

    id: UUID
    access: OperatorAccess
    action: OperatorAction
    requested: OperatorResourceRef | None
    results: tuple[OperatorResourceRef, ...]
    at: datetime
    outcome: OperatorAuditOutcome
    query_fingerprint: bytes | None = field(default=None, repr=False)
    media_request: OperatorProfileMediaRequest | None = None
    actual_source_upload_id: UUID | None = None

    def __post_init__(self) -> None:
        require_aware(self.at)
        if not self.access.is_active(self.at):
            raise ValueError("Audit requires an actual active operator revision")
        if len(set(self.results)) != len(self.results):
            raise ValueError("Audit result references must be distinct actual resources")
        self._validate_media()
        if self.action in (
            OperatorAction.SEARCH_ACCOUNTS,
            OperatorAction.SEARCH_EVENTS,
            OperatorAction.SEARCH_REPORTS,
            OperatorAction.SEARCH_SUPPORT_CASES,
        ):
            self._validate_search()
        else:
            self._validate_read()

    def _validate_search(self) -> None:
        if (
            self.requested is not None
            or self.outcome != OperatorAuditOutcome.SEARCH
            or self.query_fingerprint is None
            or len(self.query_fingerprint) != FINGERPRINT_BYTES
        ):
            raise ValueError(
                "Search audit requires only its exact query fingerprint and result refs"
            )
        kind, limit = {
            OperatorAction.SEARCH_ACCOUNTS: (
                OperatorResourceKind.ACCOUNT,
                OPERATOR_ACCOUNT_PAGE_SIZE,
            ),
            OperatorAction.SEARCH_EVENTS: (OperatorResourceKind.EVENT, OPERATOR_EVENT_PAGE_SIZE),
            OperatorAction.SEARCH_REPORTS: (OperatorResourceKind.REPORT, OPERATOR_EVENT_PAGE_SIZE),
            OperatorAction.SEARCH_SUPPORT_CASES: (
                OperatorResourceKind.SUPPORT_CASE,
                OPERATOR_EVENT_PAGE_SIZE,
            ),
        }[self.action]
        if len(self.results) > limit or any(ref.kind != kind for ref in self.results):
            raise ValueError("Account/event search audit exceeds its actual bounded results")

    def _validate_read(self) -> None:
        expected = {
            OperatorAction.READ_ACCOUNT: OperatorResourceKind.ACCOUNT,
            OperatorAction.READ_EVENT: OperatorResourceKind.EVENT,
            OperatorAction.READ_AUDIT: OperatorResourceKind.AUDIT,
            OperatorAction.READ_REPORT: OperatorResourceKind.REPORT,
            OperatorAction.READ_SUPPORT_CASE: OperatorResourceKind.SUPPORT_CASE,
            OperatorAction.READ_MEDIA: OperatorResourceKind.PROFILE_MEDIA,
            OperatorAction.READ_CONVERSATION_MESSAGES: OperatorResourceKind.CONVERSATION,
        }.get(self.action)
        if (
            self.requested is None
            or self.requested.kind != expected
            or self.outcome not in (OperatorAuditOutcome.READ, OperatorAuditOutcome.NOT_FOUND)
            or self.query_fingerprint is not None
        ):
            raise ValueError("Inspection audit requires its fixed actual resource and outcome")
        if self.outcome == OperatorAuditOutcome.NOT_FOUND:
            if self.results:
                raise ValueError("Not-found audit cannot invent returned resources")
        elif self.action in (
            OperatorAction.READ_ACCOUNT,
            OperatorAction.READ_EVENT,
            OperatorAction.READ_AUDIT,
            OperatorAction.READ_REPORT,
            OperatorAction.READ_SUPPORT_CASE,
            OperatorAction.READ_MEDIA,
        ):
            if self.results != (self.requested,):
                raise ValueError("Inspection audit must reference its actual returned resource")
        elif len(self.results) > OPERATOR_MESSAGE_PAGE_SIZE or any(
            ref.kind != OperatorResourceKind.MESSAGE for ref in self.results
        ):
            raise ValueError("Message inspection audit exceeds its actual bounded results")

    def _validate_media(self) -> None:
        request = self.media_request
        if self.action != OperatorAction.READ_MEDIA:
            if request is not None or self.actual_source_upload_id is not None:
                raise ValueError("Only actual media inspection may contain media source metadata")
            return
        if (
            request is None
            or self.requested is None
            or self.requested.id != request.upload_id
            or self.actual_source_upload_id not in (None, request.upload_id)
            or (self.outcome == OperatorAuditOutcome.READ and self.actual_source_upload_id is None)
        ):
            raise ValueError(
                "Media inspection requires its exact requested and actual source shape"
            )
