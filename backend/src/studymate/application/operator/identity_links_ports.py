"""Narrow private inspection ports; opaque cursors do not confer authority."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.identity_links_data import (
    OperatorIdentityAccount,
    OperatorIdentityLink,
)
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.time import require_aware


@dataclass(frozen=True, slots=True)
class OperatorIdentityLinksPosition:
    as_of: datetime
    before_created_at: datetime
    before_account_id: UUID

    def __post_init__(self) -> None:
        require_aware(self.as_of)
        require_aware(self.before_created_at)
        if self.before_created_at > self.as_of:
            raise ValueError("Identity association position exceeds its fixed source anchor")


@dataclass(frozen=True, slots=True)
class OperatorIdentityLinksWindow:
    as_of: datetime
    before: OperatorIdentityLinksPosition | None


class OperatorIdentityLinksCursorCodec(Protocol):
    def encode_links(
        self,
        scope: OperatorCursorScope,
        target_id: UUID,
        fingerprint: bytes,
        position: OperatorIdentityLinksPosition,
    ) -> str: ...

    def decode_links(
        self,
        scope: OperatorCursorScope,
        target_id: UUID,
        fingerprint: bytes,
        token: str,
        now: datetime,
    ) -> OperatorIdentityLinksPosition: ...


class OperatorIdentityLinksTransaction(OperatorAuditTransaction, Protocol):
    async def identity_links_target(self, account_id: UUID) -> OperatorIdentityAccount | None: ...

    async def identity_links(
        self,
        target: OperatorIdentityAccount,
        window: OperatorIdentityLinksWindow,
    ) -> tuple[OperatorIdentityLink, ...]:
        """At most51 distinct other accounts, created_at/idDESC; actual one-hop sources only."""
        ...


class OperatorIdentityLinksUnitOfWork(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OperatorIdentityLinksTransaction]: ...
