"""Bounded retained disclosure search and exact page ACK read ports."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.connection_requests import (
    MAX_OPERATOR_REQUEST_VERSION,
    OperatorRequestAcknowledgement,
    OperatorRequestRoot,
)
from studymate.domain.operator.request_disclosures import OperatorRetainedDisclosure
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorDisclosureFilters:
    viewer_id: UUID | None = None
    stored_version: int | None = None
    created_from: datetime | None = None
    created_before: datetime | None = None
    disclosure_id: UUID | None = None
    acknowledgement_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.stored_version is not None and (
            isinstance(self.stored_version, bool)
            or not 1 <= self.stored_version <= MAX_OPERATOR_REQUEST_VERSION
        ):
            raise ValueError("Disclosure filter requires a bounded actual version")
        for value in (self.created_from, self.created_before):
            if value is not None:
                require_aware(value)
        if (
            self.created_from is not None
            and self.created_before is not None
            and self.created_from >= self.created_before
        ):
            raise ValueError("Disclosure filter requires a nonempty half-open interval")

    def fingerprint_parts(self) -> tuple[str, ...]:
        return (
            "operator.request-disclosures.v1",
            str(self.viewer_id) if self.viewer_id is not None else "",
            str(self.stored_version) if self.stored_version is not None else "",
            self.created_from.astimezone(UTC).isoformat() if self.created_from else "",
            self.created_before.astimezone(UTC).isoformat() if self.created_before else "",
            str(self.disclosure_id) if self.disclosure_id is not None else "",
            str(self.acknowledgement_id) if self.acknowledgement_id is not None else "",
        )

    def matches(self, row: OperatorRetainedDisclosure) -> bool:
        # ACK filter is separately checked against the exact page-linked actual ACK rows.
        return not (
            (self.viewer_id is not None and row.viewer_id != self.viewer_id)
            or (self.stored_version is not None and row.stored_version != self.stored_version)
            or (self.disclosure_id is not None and row.id != self.disclosure_id)
            or (self.created_from is not None and row.created_at < self.created_from)
            or (self.created_before is not None and row.created_at >= self.created_before)
        )


@dataclass(frozen=True, slots=True)
class OperatorDisclosurePosition:
    anchor_created_at: datetime
    anchor_disclosure_id: UUID
    before_created_at: datetime
    before_disclosure_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.anchor_created_at)
        require_aware(self.before_created_at)
        if (self.before_created_at, self.before_disclosure_id.int) > (
            self.anchor_created_at,
            self.anchor_disclosure_id.int,
        ):
            raise ValueError("Disclosure position exceeds its actual metadata anchor")


class OperatorDisclosureCursorCodec(Protocol):
    def encode(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        request_id: UUID,
        fingerprint: bytes,
        position: OperatorDisclosurePosition,
    ) -> str: ...
    def decode(
        self,
        scope: OperatorCursorScope,
        account_id: UUID,
        request_id: UUID,
        fingerprint: bytes,
        token: str,
    ) -> OperatorDisclosurePosition: ...


class OperatorDisclosureTransaction(OperatorAuditTransaction, Protocol):
    async def disclosure_account(self, account_id: UUID) -> UUID | None: ...
    async def disclosure_request(
        self, account_id: UUID, request_id: UUID
    ) -> OperatorRequestRoot | None: ...
    async def request_disclosures(
        self,
        account_id: UUID,
        request_id: UUID,
        filters: OperatorDisclosureFilters,
        position: OperatorDisclosurePosition | None,
    ) -> tuple[OperatorRetainedDisclosure, ...]: ...
    async def disclosure_page_acknowledgements(
        self,
        account_id: UUID,
        request_id: UUID,
        disclosure_ids: tuple[UUID, ...],
    ) -> tuple[OperatorRequestAcknowledgement, ...]: ...


class OperatorDisclosureUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorDisclosureTransaction]: ...
