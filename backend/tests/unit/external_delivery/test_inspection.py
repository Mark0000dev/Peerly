"""Audit failure/authority and opaque cursor regressions; shared enums land with0055."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from studymate.application.errors import StorageUnavailableError
from studymate.application.external_delivery.inspection import (
    ReadDeliverySource,
    SearchDeliverySources,
    SourceFilters,
)
from studymate.application.identity.sessions import UnauthenticatedError
from studymate.application.operator.authority import OperatorAccessDeniedError
from studymate.application.operator.cursors import InvalidOperatorCursorError
from studymate.domain.external_delivery.inspection import PAGE_SIZE, SourceDetail, SourceSummary
from studymate.domain.external_delivery.sources import CaptureMode, SourceKind
from studymate.domain.operator.audit import OperatorAuditOutcome
from studymate.infrastructure.external_delivery.cursors import FernetSourceCursorCodec
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.unit.identity_store import CREDENTIAL, NOW
from tests.unit.operator.store import Store

CODEC = FernetSourceCursorCodec.from_key(b"k" * 32)


class InspectionStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.rows: tuple[SourceSummary, ...] = ()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["InspectionStore"]:
        async with super().transaction():
            yield self

    async def sources(
        self, filters: SourceFilters, before_id: UUID | None
    ) -> tuple[SourceSummary, ...]:
        self.queried()
        return tuple(
            row
            for row in self.rows
            if (before_id is None or row.id.int < before_id.int)
            and (filters.actor_id is None or row.actor_id == filters.actor_id)
            and (filters.kind is None or row.kind == filters.kind)
        )[: PAGE_SIZE + 1]

    async def source(self, source_id: UUID) -> SourceDetail | None:
        self.queried()
        assert source_id.int > 0
        return None


def search(store: InspectionStore) -> SearchDeliverySources:
    return SearchDeliverySources(
        store, Sha256SessionHasher(), HmacIntentFingerprinter(b"h" * 32), CODEC
    )


async def test_source_pagination_audits_visible_refs_and_cannot_change_query_or_grant() -> None:
    store = InspectionStore()
    store.assign_explicit_operator()
    store.rows = tuple(
        SourceSummary(
            UUID(int=index),
            SourceKind.CLIENT_OBSERVATION,
            uuid4(),
            UUID(int=100),
            NOW,
            CaptureMode.LIVE,
            1,
            None,
            None,
        )
        for index in range(PAGE_SIZE + 1, 0, -1)
    )
    first = await search(store)(CREDENTIAL, SourceFilters())
    assert len(first.sources) == PAGE_SIZE
    assert first.next_cursor is not None
    assert tuple(ref.id for ref in store.audit[-1].results) == tuple(
        row.id for row in first.sources
    )
    second = await search(store)(CREDENTIAL, SourceFilters(), first.next_cursor)
    assert len(second.sources) == 1
    with pytest.raises(InvalidOperatorCursorError):
        await search(store)(CREDENTIAL, SourceFilters(actor_id=uuid4()), first.next_cursor)
    assert store.access is not None
    store.access = replace(store.access, version=2)
    with pytest.raises(InvalidOperatorCursorError):
        await search(store)(CREDENTIAL, SourceFilters(), first.next_cursor)


async def test_no_implicit_operator_and_audit_failure_returns_no_metadata() -> None:
    store = InspectionStore()
    with pytest.raises(OperatorAccessDeniedError):
        await search(store)(CREDENTIAL, SourceFilters())
    assert store.private_queries == 0
    store.assign_explicit_operator()
    store.fail_audit = True
    with pytest.raises(StorageUnavailableError):
        await search(store)(CREDENTIAL, SourceFilters())
    assert not store.audit
    store.fail_audit = False
    store.expire_after_audit = True
    with pytest.raises(UnauthenticatedError):
        await ReadDeliverySource(store, Sha256SessionHasher())(CREDENTIAL, uuid4())
    assert not store.audit


async def test_missing_source_retains_exact_not_found_audit() -> None:
    store = InspectionStore()
    store.assign_explicit_operator()
    identifier = uuid4()
    assert await ReadDeliverySource(store, Sha256SessionHasher())(CREDENTIAL, identifier) is None
    audit = store.audit[-1]
    assert audit.requested is not None
    assert audit.requested.id == identifier
    assert audit.results == ()
    assert audit.outcome == OperatorAuditOutcome.NOT_FOUND
