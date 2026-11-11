"""Actual explicit operator grant and durable audit before any metadata returns."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.external_delivery.inspection import PAGE_SIZE, SourceDetail, SourceSummary
from studymate.domain.external_delivery.sources import SourceKind
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)


@dataclass(frozen=True, slots=True)
class SourceFilters:
    actor_id: UUID | None = None
    kind: SourceKind | None = None

    def parts(self) -> tuple[str, ...]:
        return (
            "delivery-source-search.v1",
            str(self.actor_id or ""),
            self.kind.value if self.kind else "",
        )


@dataclass(frozen=True, slots=True)
class SourcesPage:
    sources: tuple[SourceSummary, ...]
    next_cursor: str | None


class SourceCursorCodec(Protocol):
    def encode(self, scope: OperatorCursorScope, fingerprint: bytes, before_id: UUID) -> str: ...
    def decode(self, scope: OperatorCursorScope, fingerprint: bytes, token: str) -> UUID: ...


class SourceInspectionTransaction(OperatorAuditTransaction, Protocol):
    async def sources(
        self, filters: SourceFilters, before_id: UUID | None
    ) -> tuple[SourceSummary, ...]: ...
    async def source(self, source_id: UUID) -> SourceDetail | None: ...


class SourceInspectionUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[SourceInspectionTransaction]: ...


@dataclass(frozen=True, slots=True)
class SearchDeliverySources:
    unit_of_work: SourceInspectionUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursors: SourceCursorCodec

    async def __call__(
        self, credential: SessionCredential, filters: SourceFilters, cursor: str | None = None
    ) -> SourcesPage:
        fingerprint = await self.fingerprinter.fingerprint(filters.parts())
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            before = self.cursors.decode(scope, fingerprint, cursor) if cursor is not None else None
            rows = await transaction.sources(filters, before)
            if len(rows) > PAGE_SIZE + 1:
                raise RuntimeError("Delivery source reader exceeded its bounded metadata page")
            previous = before
            for row in rows:
                if (
                    (previous is not None and row.id.int >= previous.int)
                    or (filters.actor_id is not None and row.actor_id != filters.actor_id)
                    or (filters.kind is not None and row.kind != filters.kind)
                ):
                    raise RuntimeError("Delivery source reader violated actual query scope/order")
                previous = row.id
            visible = rows[:PAGE_SIZE]
            next_cursor = (
                self.cursors.encode(scope, fingerprint, visible[-1].id)
                if len(rows) > PAGE_SIZE
                else None
            )
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.SEARCH_DELIVERY_SOURCES,
                    None,
                    tuple(
                        OperatorResourceRef(OperatorResourceKind.DELIVERY_SOURCE, row.id)
                        for row in visible
                    ),
                    await transaction.now(),
                    OperatorAuditOutcome.SEARCH,
                    fingerprint,
                )
            )
            await finish_operator(transaction, principal)
            return SourcesPage(visible, next_cursor)


@dataclass(frozen=True, slots=True)
class ReadDeliverySource:
    unit_of_work: SourceInspectionUnitOfWork
    hasher: SessionHasher

    async def __call__(self, credential: SessionCredential, source_id: UUID) -> SourceDetail | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            detail = await transaction.source(source_id)
            if detail is not None and (
                detail.summary.id != source_id or detail.source.id != source_id
            ):
                raise RuntimeError("Delivery inspection returned another actual source")
            ref = OperatorResourceRef(OperatorResourceKind.DELIVERY_SOURCE, source_id)
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_DELIVERY_SOURCE,
                    ref,
                    (ref,) if detail else (),
                    await transaction.now(),
                    OperatorAuditOutcome.READ if detail else OperatorAuditOutcome.NOT_FOUND,
                )
            )
            await finish_operator(transaction, principal)
            return detail
