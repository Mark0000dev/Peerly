"""Privileged retained disclosure listing with mandatory transactional account audit."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import (
    OperatorPrincipal,
    finish_operator,
    require_operator,
)
from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.disclosure_ports import (
    OperatorDisclosureCursorCodec,
    OperatorDisclosureFilters,
    OperatorDisclosurePosition,
    OperatorDisclosureUnitOfWork,
)
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)
from studymate.domain.operator.connection_requests import (
    OperatorRequestAcknowledgement,
    OperatorRequestRoot,
)
from studymate.domain.operator.request_disclosures import (
    OPERATOR_DISCLOSURE_PAGE_SIZE,
    OperatorRetainedDisclosure,
)


@dataclass(frozen=True, slots=True)
class OperatorRequestDisclosuresPage:
    account_id: UUID
    request: OperatorRequestRoot
    disclosures: tuple[OperatorRetainedDisclosure, ...]
    acknowledgements: tuple[OperatorRequestAcknowledgement, ...]
    next_cursor: str | None
    anchor_created_at: datetime | None
    anchor_disclosure_id: UUID | None
    observed_at: datetime


async def audit_disclosure_account(
    transaction: OperatorAuditTransaction,
    principal: OperatorPrincipal,
    account_id: UUID,
    *,
    found: bool,
) -> None:
    resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
    await transaction.save_operator_audit(
        OperatorAudit(
            uuid4(),
            principal.access,
            OperatorAction.READ_ACCOUNT,
            resource,
            (resource,) if found else (),
            await transaction.now(),
            OperatorAuditOutcome.READ if found else OperatorAuditOutcome.NOT_FOUND,
        )
    )
    await finish_operator(transaction, principal)


def validate_disclosures(
    rows: tuple[OperatorRetainedDisclosure, ...],
    root: OperatorRequestRoot,
    filters: OperatorDisclosureFilters,
    position: OperatorDisclosurePosition | None,
) -> None:
    if len(rows) > OPERATOR_DISCLOSURE_PAGE_SIZE + 1:
        raise RuntimeError("Disclosure source exceeded its bounded metadata page")
    previous = (
        (position.before_created_at, position.before_disclosure_id.int)
        if position is not None
        else None
    )
    for row in rows:
        key = row.created_at, row.id.int
        if (
            (row.request_id, row.sender_id, row.recipient_id)
            != (root.id, root.sender_id, root.recipient_id)
            or not filters.matches(row)
            or (previous is not None and key >= previous)
            or (
                position is not None
                and key > (position.anchor_created_at, position.anchor_disclosure_id.int)
            )
        ):
            raise RuntimeError(
                "Disclosure source violates request, participant, filter or ordering"
            )
        previous = key


def validate_disclosure_acks(
    rows: tuple[OperatorRequestAcknowledgement, ...],
    disclosures: tuple[OperatorRetainedDisclosure, ...],
    filters: OperatorDisclosureFilters,
) -> None:
    actual = {row.id: row.linked_source() for row in disclosures}
    if (
        len(rows) > len(actual)
        or len({row.id for row in rows}) != len(rows)
        or len({row.disclosure.id for row in rows}) != len(rows)
        or len({(row.viewer_id, row.stored_version) for row in rows}) != len(rows)
        or any(actual.get(row.disclosure.id) != row.disclosure for row in rows)
        or (
            filters.acknowledgement_id is not None
            and (
                len(rows) != len(disclosures)
                or any(row.id != filters.acknowledgement_id for row in rows)
            )
        )
    ):
        raise RuntimeError("Disclosure ACK source differs from exact page-linked actual rows")


@dataclass(frozen=True, slots=True)
class ReadOperatorRequestDisclosures:
    unit_of_work: OperatorDisclosureUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter
    cursor_codec: OperatorDisclosureCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        request_id: UUID,
        filters: OperatorDisclosureFilters,
        cursor: str | None = None,
    ) -> OperatorRequestDisclosuresPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            actual = await transaction.disclosure_account(account_id)
            if actual is None:
                await audit_disclosure_account(transaction, principal, account_id, found=False)
                return None
            if actual != account_id:
                raise RuntimeError("Disclosure account source belongs to another account")
            root = await transaction.disclosure_request(account_id, request_id)
            if root is None:
                await audit_disclosure_account(transaction, principal, account_id, found=True)
                return None
            if root.id != request_id or not root.includes(account_id):
                raise RuntimeError(
                    "Disclosure request source belongs to another account or request"
                )
            digest = await self.fingerprinter.fingerprint(filters.fingerprint_parts())
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            position = (
                self.cursor_codec.decode(scope, account_id, request_id, digest, cursor)
                if cursor is not None
                else None
            )
            rows = await transaction.request_disclosures(account_id, request_id, filters, position)
            validate_disclosures(rows, root, filters, position)
            anchor_at, anchor_id = (
                (position.anchor_created_at, position.anchor_disclosure_id)
                if position is not None
                else (rows[0].created_at, rows[0].id)
                if rows
                else (None, None)
            )
            visible = rows[:OPERATOR_DISCLOSURE_PAGE_SIZE]
            continuation = None
            if len(rows) > OPERATOR_DISCLOSURE_PAGE_SIZE:
                if anchor_at is None or anchor_id is None:
                    raise RuntimeError("Disclosure source lost its continuation anchor")
                continuation = self.cursor_codec.encode(
                    scope,
                    account_id,
                    request_id,
                    digest,
                    OperatorDisclosurePosition(
                        anchor_at, anchor_id, visible[-1].created_at, visible[-1].id
                    ),
                )
            acks = await transaction.disclosure_page_acknowledgements(
                account_id, request_id, tuple(row.id for row in visible)
            )
            validate_disclosure_acks(acks, visible, filters)
            observed = await transaction.now()
            await audit_disclosure_account(transaction, principal, account_id, found=True)
            return OperatorRequestDisclosuresPage(
                account_id, root, visible, acks, continuation, anchor_at, anchor_id, observed
            )
