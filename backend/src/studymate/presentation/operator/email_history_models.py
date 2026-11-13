"""Safe retained metadata only; delivered_at records SMTP acceptance, never inbox arrival."""

from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.email_history import OperatorEmailHistoryPage
from studymate.domain.operator.email_history import (
    EMAIL_HISTORY_PAGE_SIZE,
    StoredEmailDeliveryError,
    StoredEmailDeliveryStatus,
)
from studymate.presentation.operator.models import ClosedModel


class OperatorEmailHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class EmailHistoryDeliveryResponse(ClosedModel):
    id: UUID
    status: StoredEmailDeliveryStatus
    created_at: AwareDatetime
    due_at: AwareDatetime
    attempts: int = Field(ge=0, le=3)
    delivered_at: AwareDatetime | None = Field(
        description="SMTP/provider acceptance timestamp; not proof of inbox delivery or reading"
    )
    last_error: StoredEmailDeliveryError | None
    origin_request_id: UUID | None
    origin_action_id: UUID | None
    origin_trace_id: str | None
    origin_span_id: str | None


class EmailHistoryManualVerificationResponse(ClosedModel):
    id: UUID
    operator_id: UUID
    operator_access_version: int = Field(ge=1)
    event_id: UUID
    verified_at: AwareDatetime


class EmailHistoryChallengeResponse(ClosedModel):
    id: UUID
    account_id: UUID
    session_id: UUID
    email: str = Field(repr=False)
    created_at: AwareDatetime
    expires_at: AwareDatetime
    resend_at: AwareDatetime
    attempts: int = Field(ge=0, le=5)
    consumed_at: AwareDatetime | None
    superseded_at: AwareDatetime | None
    delivery: EmailHistoryDeliveryResponse | None
    manual_verification: EmailHistoryManualVerificationResponse | None


class OperatorEmailHistoryResponse(ClosedModel):
    account_id: UUID
    challenges: tuple[EmailHistoryChallengeResponse, ...] = Field(
        max_length=EMAIL_HISTORY_PAGE_SIZE, repr=False
    )
    next_cursor: str | None
    as_of: AwareDatetime = Field(
        description=(
            "Upper creation boundary for challenges only; "
            "mutable delivery/verification state is freshly read on every page"
        )
    )


def email_history_response(value: OperatorEmailHistoryPage) -> OperatorEmailHistoryResponse:
    return OperatorEmailHistoryResponse(
        account_id=value.account_id,
        challenges=tuple(
            EmailHistoryChallengeResponse(
                id=row.id,
                account_id=row.account_id,
                session_id=row.session_id,
                email=row.email,
                created_at=row.created_at,
                expires_at=row.expires_at,
                resend_at=row.resend_at,
                attempts=row.attempts,
                consumed_at=row.consumed_at,
                superseded_at=row.superseded_at,
                delivery=EmailHistoryDeliveryResponse(
                    id=row.delivery.id,
                    status=row.delivery.status,
                    created_at=row.delivery.created_at,
                    due_at=row.delivery.due_at,
                    attempts=row.delivery.attempts,
                    delivered_at=row.delivery.delivered_at,
                    last_error=row.delivery.last_error,
                    origin_request_id=row.delivery.origin_request_id,
                    origin_action_id=row.delivery.origin_action_id,
                    origin_trace_id=row.delivery.origin_trace_id,
                    origin_span_id=row.delivery.origin_span_id,
                )
                if row.delivery is not None
                else None,
                manual_verification=EmailHistoryManualVerificationResponse(
                    id=row.manual_verification.id,
                    operator_id=row.manual_verification.operator_id,
                    operator_access_version=row.manual_verification.operator_access_version,
                    event_id=row.manual_verification.event_id,
                    verified_at=row.manual_verification.verified_at,
                )
                if row.manual_verification is not None
                else None,
            )
            for row in value.challenges
        ),
        next_cursor=value.next_cursor,
        as_of=value.as_of,
    )
