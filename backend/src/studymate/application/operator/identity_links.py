"""Read a retained account aggregate and its direct stored-claim references with audit."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from studymate.application.identity.sessions import SessionCredential, SessionHasher
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.application.operator.cursors import OperatorCursorScope
from studymate.application.operator.identity_links_data import (
    IDENTITY_LINKS_PAGE_SIZE,
    OperatorIdentityAccount,
    OperatorIdentityLink,
)
from studymate.application.operator.identity_links_ports import (
    OperatorIdentityLinksCursorCodec,
    OperatorIdentityLinksPosition,
    OperatorIdentityLinksUnitOfWork,
    OperatorIdentityLinksWindow,
)
from studymate.domain.operator.audit import (
    OperatorAction,
    OperatorAudit,
    OperatorAuditOutcome,
    OperatorResourceKind,
    OperatorResourceRef,
)


@dataclass(frozen=True, slots=True)
class OperatorIdentityLinksPage:
    target: OperatorIdentityAccount = field(repr=False)
    links: tuple[OperatorIdentityLink, ...] = field(repr=False)
    next_cursor: str | None
    as_of: datetime


@dataclass(frozen=True, slots=True)
class ReadOperatorIdentityLinks:
    unit_of_work: OperatorIdentityLinksUnitOfWork
    hasher: SessionHasher
    cursor_codec: OperatorIdentityLinksCursorCodec

    async def __call__(
        self,
        credential: SessionCredential,
        account_id: UUID,
        cursor: str | None = None,
    ) -> OperatorIdentityLinksPage | None:
        async with self.unit_of_work.transaction() as transaction:
            principal = await require_operator(transaction, credential, self.hasher)
            resource = OperatorResourceRef(OperatorResourceKind.ACCOUNT, account_id)
            target = await transaction.identity_links_target(account_id)
            if target is None:
                await transaction.save_operator_audit(
                    OperatorAudit(
                        uuid4(),
                        principal.access,
                        OperatorAction.READ_ACCOUNT,
                        resource,
                        (),
                        await transaction.now(),
                        OperatorAuditOutcome.NOT_FOUND,
                    )
                )
                await finish_operator(transaction, principal)
                return None
            if target.account_id != account_id:
                raise RuntimeError("Retained identity source belongs to a different account")
            now = await transaction.now()
            scope = OperatorCursorScope(principal.access.account_id, principal.access.version)
            fingerprint = target.claim_fingerprint()
            position = (
                self.cursor_codec.decode_links(scope, account_id, fingerprint, cursor, now)
                if cursor is not None
                else None
            )
            window = OperatorIdentityLinksWindow(
                position.as_of if position is not None else now, position
            )
            rows = await transaction.identity_links(target, window)
            validate_links(target, window, rows)
            visible = rows[:IDENTITY_LINKS_PAGE_SIZE]
            continuation = (
                self.cursor_codec.encode_links(
                    scope,
                    account_id,
                    fingerprint,
                    OperatorIdentityLinksPosition(
                        window.as_of,
                        visible[-1].account.created_at,
                        visible[-1].account.account_id,
                    ),
                )
                if len(rows) > IDENTITY_LINKS_PAGE_SIZE
                else None
            )
            # READ_ACCOUNT inspects one account aggregate; links are not independent detail reads.
            await transaction.save_operator_audit(
                OperatorAudit(
                    uuid4(),
                    principal.access,
                    OperatorAction.READ_ACCOUNT,
                    resource,
                    (resource,),
                    await transaction.now(),
                    OperatorAuditOutcome.READ,
                )
            )
            await finish_operator(transaction, principal)
            return OperatorIdentityLinksPage(target, visible, continuation, window.as_of)


def validate_links(
    target: OperatorIdentityAccount,
    window: OperatorIdentityLinksWindow,
    rows: tuple[OperatorIdentityLink, ...],
) -> None:
    if len(rows) > IDENTITY_LINKS_PAGE_SIZE + 1:
        raise RuntimeError("Identity association exceeded its bounded source page")
    previous = (
        (window.before.before_created_at, window.before.before_account_id)
        if window.before is not None
        else None
    )
    for row in rows:
        account = row.account
        key = (account.created_at, account.account_id)
        if (
            account.account_id == target.account_id
            or account.created_at > window.as_of
            or (previous is not None and key >= previous)
        ):
            raise RuntimeError("Identity association source violates owner or stable ordering")
        google = account.google
        institutional = account.institutional
        shared_google = (
            google is not None
            and target.google is not None
            and google.issuer == target.google.issuer
            and google.subject == target.google.subject
            and google.created_at <= window.as_of
        )
        shared_email = (
            institutional is not None
            and target.institutional is not None
            and institutional.email == target.institutional.email
            and institutional.verified_at <= window.as_of
        )
        if (shared_google, shared_email) != (
            row.shared_google_claim,
            row.shared_institutional_email,
        ):
            raise RuntimeError("Identity association must reflect its exact stored direct sources")
        previous = key
