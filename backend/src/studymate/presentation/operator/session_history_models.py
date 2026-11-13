"""Stored timestamps only, with no inferred active flag or authentication material."""

from uuid import UUID

from pydantic import AwareDatetime, Field

from studymate.application.operator.session_history import OperatorSessionHistoryPage
from studymate.domain.operator.session_history import SESSION_HISTORY_PAGE_SIZE
from studymate.presentation.operator.models import ClosedModel


class OperatorSessionHistoryQuery(ClosedModel):
    cursor: str | None = Field(default=None, min_length=1, max_length=1024, repr=False)


class SessionHistoryEntryResponse(ClosedModel):
    id: UUID
    account_id: UUID
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None


class OperatorSessionHistoryResponse(ClosedModel):
    account_id: UUID
    sessions: tuple[SessionHistoryEntryResponse, ...] = Field(
        max_length=SESSION_HISTORY_PAGE_SIZE, repr=False
    )
    next_cursor: str | None
    as_of: AwareDatetime = Field(
        description=(
            "Upper issuance boundary only; stored revocation timestamps are freshly read. "
            "Timestamps are not a statement of effective account/session authorization."
        )
    )


def session_history_response(value: OperatorSessionHistoryPage) -> OperatorSessionHistoryResponse:
    return OperatorSessionHistoryResponse(
        account_id=value.account_id,
        sessions=tuple(
            SessionHistoryEntryResponse(
                id=row.id,
                account_id=row.account_id,
                issued_at=row.issued_at,
                expires_at=row.expires_at,
                revoked_at=row.revoked_at,
            )
            for row in value.sessions
        ),
        next_cursor=value.next_cursor,
        as_of=value.as_of,
    )
