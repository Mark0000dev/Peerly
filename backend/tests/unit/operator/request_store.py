from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

from studymate.application.operator.request_ports import (
    OperatorRequestFilters,
    OperatorRequestHistoryHead,
    OperatorRequestHistoryWindow,
    OperatorRequestPosition,
)
from studymate.domain.discovery import DiscoveryMode
from studymate.domain.operator.connection_requests import (
    OPERATOR_REQUEST_PAGE_SIZE,
    OperatorRequestAcknowledgement,
    OperatorRequestDisclosure,
    OperatorRequestOrigin,
    OperatorRequestPreview,
    OperatorRequestRevision,
    OperatorRequestRoot,
    OperatorRequestSnapshot,
)
from studymate.domain.requests.states import RequestState
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store

DECLINE_VERSION = 3
REQUEST = UUID(int=1201)
PEER = UUID(int=1202)
RAW_TEXT = "  Original private reviewed request  "
RAW_NOTE = " Private separate note "
RAW_SOURCE = ' { "retired_schema": "Private retained academic context" }\n'


def root(request_id: UUID = REQUEST, *, incoming: bool = False) -> OperatorRequestRoot:
    return OperatorRequestRoot(
        request_id,
        UUID(int=1206),
        PEER if incoming else TARGET,
        TARGET if incoming else PEER,
        UUID(int=1203),
        DiscoveryMode.FIND_HELP,
        UUID(int=1204),
        NOW - timedelta(days=2),
        NOW - timedelta(days=1),
        3,
        RequestState.PENDING_DECLINE,
        OperatorRequestOrigin(None, uuid4(), "legacy-trace", None),
    )


def snapshot(request_id: UUID = REQUEST, *, incoming: bool = False) -> OperatorRequestSnapshot:
    value = root(request_id, incoming=incoming)
    preview = OperatorRequestPreview(
        value.preview_id,
        value.sender_id,
        value.recipient_id,
        value.mode,
        value.subject_id,
        NOW,
        RAW_SOURCE,
        UUID(int=1205),
        7,
        None,
        None,
        None,
        3,
    )
    return OperatorRequestSnapshot(value, RAW_TEXT, RAW_NOTE, preview)


def revision(version: int, request_id: UUID = REQUEST) -> OperatorRequestRevision:
    at = NOW - timedelta(minutes=version)
    state = (
        RequestState.PENDING
        if version == 1
        else RequestState.PENDING_DECLINE
        if version == DECLINE_VERSION
        else RequestState.WITHDRAWN
    )
    return OperatorRequestRevision(
        request_id,
        version,
        state,
        at,
        at + timedelta(seconds=10) if version == DECLINE_VERSION else None,
        None,
    )


def ack(
    version: int, viewer_id: UUID = TARGET, request_id: UUID = REQUEST
) -> OperatorRequestAcknowledgement:
    disclosure = OperatorRequestDisclosure(
        uuid4(), viewer_id, request_id, version, NOW, OperatorRequestOrigin()
    )
    return OperatorRequestAcknowledgement(
        uuid4(), viewer_id, request_id, version, NOW, OperatorRequestOrigin(), disclosure
    )


class RequestStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.accounts = {TARGET, PEER}
        self.snapshots = {REQUEST: snapshot()}
        self.revisions = {REQUEST: tuple(revision(i) for i in range(1, 4))}
        self.acknowledgements: tuple[OperatorRequestAcknowledgement, ...] = ()
        self.account_override: UUID | None = None
        self.head_override: OperatorRequestHistoryHead | None = None
        self.root_override: tuple[OperatorRequestRoot, ...] | None = None
        self.revision_override: tuple[OperatorRequestRevision, ...] | None = None
        self.ack_override: tuple[OperatorRequestAcknowledgement, ...] | None = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["RequestStore"]:
        async with Store.transaction(self):
            yield self

    async def request_account(self, account_id: UUID) -> UUID | None:
        self.queried()
        return (
            self.account_override
            if self.account_override is not None
            else account_id
            if account_id in self.accounts
            else None
        )

    async def request_roots(
        self,
        account_id: UUID,
        filters: OperatorRequestFilters,
        position: OperatorRequestPosition | None,
    ) -> tuple[OperatorRequestRoot, ...]:
        self.queried()
        if self.root_override is not None:
            return self.root_override
        rows = (
            value.root
            for value in self.snapshots.values()
            if filters.matches(value.root, account_id)
            and (
                position is None
                or (
                    (value.root.sent_at, value.root.id.int)
                    <= (position.anchor_sent_at, position.anchor_request_id.int)
                    and (value.root.sent_at, value.root.id.int)
                    < (position.before_sent_at, position.before_request_id.int)
                )
            )
        )
        return tuple(sorted(rows, key=lambda row: (row.sent_at, row.id.int), reverse=True))[
            : OPERATOR_REQUEST_PAGE_SIZE + 1
        ]

    async def request_history_head(
        self, account_id: UUID, request_id: UUID
    ) -> OperatorRequestHistoryHead | None:
        self.queried()
        if self.head_override is not None:
            return self.head_override
        value = self.snapshots.get(request_id)
        if value is None or not value.root.includes(account_id):
            return None
        return OperatorRequestHistoryHead(
            value, max(row.version for row in self.revisions[request_id])
        )

    async def request_revisions(
        self, account_id: UUID, request_id: UUID, window: OperatorRequestHistoryWindow
    ) -> tuple[OperatorRequestRevision, ...]:
        self.queried()
        assert self.snapshots[request_id].root.includes(account_id)
        if self.revision_override is not None:
            return self.revision_override
        return tuple(
            sorted(
                (
                    row
                    for row in self.revisions[request_id]
                    if row.version <= window.anchor_version
                    and (window.before_version is None or row.version < window.before_version)
                ),
                key=lambda row: row.version,
                reverse=True,
            )
        )[: OPERATOR_REQUEST_PAGE_SIZE + 1]

    async def request_page_acknowledgements(
        self, account_id: UUID, request_id: UUID, versions: tuple[int, ...]
    ) -> tuple[OperatorRequestAcknowledgement, ...]:
        self.queried()
        assert self.snapshots[request_id].root.includes(account_id)
        return (
            self.ack_override
            if self.ack_override is not None
            else tuple(
                row
                for row in self.acknowledgements
                if row.request_id == request_id and row.stored_version in versions
            )
        )
