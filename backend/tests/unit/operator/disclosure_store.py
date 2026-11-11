from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from uuid import UUID, uuid4

from studymate.application.errors import StorageUnavailableError
from studymate.application.operator.disclosure_ports import (
    OperatorDisclosureFilters,
    OperatorDisclosurePosition,
)
from studymate.domain.operator.connection_requests import (
    OperatorRequestAcknowledgement,
    OperatorRequestOrigin,
    OperatorRequestRoot,
)
from studymate.domain.operator.request_disclosures import (
    OPERATOR_DISCLOSURE_PAGE_SIZE,
    OperatorRetainedDisclosure,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.request_store import PEER, REQUEST, root
from tests.unit.operator.store import TARGET, Store


def disclosure(index: int = 1) -> OperatorRetainedDisclosure:
    return OperatorRetainedDisclosure(
        UUID(int=2000 + index),
        TARGET,
        REQUEST,
        1,
        TARGET,
        PEER,
        NOW + timedelta(seconds=index),
        OperatorRequestOrigin(None, uuid4(), "legacy-source", None),
    )


def linked_ack(row: OperatorRetainedDisclosure) -> OperatorRequestAcknowledgement:
    return OperatorRequestAcknowledgement(
        uuid4(),
        row.viewer_id,
        row.request_id,
        row.stored_version,
        NOW,
        OperatorRequestOrigin(None, None, None, "legacy-span"),
        row.linked_source(),
    )


class DisclosureStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.accounts = {TARGET, PEER}
        self.request = root()
        self.rows: tuple[OperatorRetainedDisclosure, ...] = (disclosure(),)
        self.acks: tuple[OperatorRequestAcknowledgement, ...] = ()
        self.account_override: UUID | None = None
        self.root_override: OperatorRequestRoot | None = None
        self.rows_override: tuple[OperatorRetainedDisclosure, ...] | None = None
        self.ack_override: tuple[OperatorRequestAcknowledgement, ...] | None = None
        self.missing_request = False
        self.fail_commit = False

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["DisclosureStore"]:
        async with Store.transaction(self):
            yield self
            if self.fail_commit:
                raise StorageUnavailableError

    async def disclosure_account(self, account_id: UUID) -> UUID | None:
        self.queried()
        return self.account_override or (account_id if account_id in self.accounts else None)

    async def disclosure_request(
        self,
        account_id: UUID,
        request_id: UUID,
    ) -> OperatorRequestRoot | None:
        self.queried()
        if self.root_override is not None:
            return self.root_override
        return (
            self.request
            if not self.missing_request
            and self.request.id == request_id
            and self.request.includes(account_id)
            else None
        )

    async def request_disclosures(
        self,
        account_id: UUID,
        request_id: UUID,
        filters: OperatorDisclosureFilters,
        position: OperatorDisclosurePosition | None,
    ) -> tuple[OperatorRetainedDisclosure, ...]:
        self.queried()
        assert self.request.includes(account_id)
        assert self.request.id == request_id
        if self.rows_override is not None:
            return self.rows_override
        filtered = (
            row
            for row in self.rows
            if filters.matches(row)
            and (
                filters.acknowledgement_id is None
                or any(
                    ack.id == filters.acknowledgement_id and ack.disclosure.id == row.id
                    for ack in self.acks
                )
            )
            and (
                position is None
                or (
                    (row.created_at, row.id.int)
                    <= (position.anchor_created_at, position.anchor_disclosure_id.int)
                    and (row.created_at, row.id.int)
                    < (position.before_created_at, position.before_disclosure_id.int)
                )
            )
        )
        return tuple(sorted(filtered, key=lambda row: (row.created_at, row.id.int), reverse=True))[
            : OPERATOR_DISCLOSURE_PAGE_SIZE + 1
        ]

    async def disclosure_page_acknowledgements(
        self,
        account_id: UUID,
        request_id: UUID,
        disclosure_ids: tuple[UUID, ...],
    ) -> tuple[OperatorRequestAcknowledgement, ...]:
        self.queried()
        assert self.request.includes(account_id)
        assert self.request.id == request_id
        return (
            self.ack_override
            if self.ack_override is not None
            else tuple(ack for ack in self.acks if ack.disclosure.id in disclosure_ids)
        )

    def seed_many(self) -> None:
        self.rows = tuple(disclosure(index) for index in range(OPERATOR_DISCLOSURE_PAGE_SIZE + 3))
        self.acks = (linked_ack(self.rows[-1]),)

    def reverse_participants(self) -> None:
        self.request = replace(self.request, sender_id=PEER, recipient_id=TARGET)
        self.rows = tuple(replace(row, sender_id=PEER, recipient_id=TARGET) for row in self.rows)
