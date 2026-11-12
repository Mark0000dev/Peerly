from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

from studymate.application.operator.identity_links_data import (
    OperatorGoogleClaim,
    OperatorIdentityAccount,
    OperatorIdentityLink,
)
from studymate.application.operator.identity_links_ports import OperatorIdentityLinksWindow
from studymate.domain.membership import GOOGLE_ISSUER
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store


def account(account_id: UUID = TARGET) -> OperatorIdentityAccount:
    return OperatorIdentityAccount(
        account_id,
        NOW - timedelta(days=1),
        None,
        NOW,
        OperatorGoogleClaim(
            UUID(int=account_id.int + 1000),
            GOOGLE_ISSUER,
            "private-shared-subject",
            NOW - timedelta(days=1),
            NOW,
        ),
        None,
    )


class LinksStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.target: OperatorIdentityAccount | None = account()
        self.rows: tuple[OperatorIdentityLink, ...] = ()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["LinksStore"]:
        async with Store.transaction(self):
            yield self

    async def identity_links_target(self, account_id: UUID) -> OperatorIdentityAccount | None:
        self.queried()
        return self.target if self.target is None or self.target.account_id == account_id else None

    async def identity_links(
        self, target: OperatorIdentityAccount, window: OperatorIdentityLinksWindow
    ) -> tuple[OperatorIdentityLink, ...]:
        self.queried()
        assert self.target == target
        return tuple(
            row
            for row in self.rows
            if row.account.created_at <= window.as_of
            and (
                window.before is None
                or (row.account.created_at, row.account.account_id)
                < (window.before.before_created_at, window.before.before_account_id)
            )
        )[:51]
