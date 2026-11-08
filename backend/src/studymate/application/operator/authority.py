from dataclasses import dataclass, field

from studymate.application.identity.sessions import (
    IdentitySnapshot,
    SessionCredential,
    SessionHasher,
    UnauthenticatedError,
    require_session_identity,
)
from studymate.application.operator.ports import OperatorAuditTransaction
from studymate.domain.operator.access import OperatorAccess


class OperatorAccessDeniedError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class OperatorPrincipal:
    identity: IdentitySnapshot = field(repr=False)
    access: OperatorAccess


async def require_operator(
    transaction: OperatorAuditTransaction, credential: SessionCredential, hasher: SessionHasher
) -> OperatorPrincipal:
    identity, _ = await require_session_identity(transaction, await hasher.digest(credential))
    if identity.banned:
        raise OperatorAccessDeniedError
    access = await transaction.operator_access(identity.session.account_id)
    now = await transaction.now()
    if not identity.session.is_active(now):
        raise UnauthenticatedError
    if access is None or not access.is_active(now):
        raise OperatorAccessDeniedError
    if access.account_id != identity.session.account_id:
        raise RuntimeError("Operator access belongs to another authenticated account")
    return OperatorPrincipal(identity, access)


async def finish_operator(
    transaction: OperatorAuditTransaction, principal: OperatorPrincipal
) -> None:
    if not principal.identity.session.is_active(await transaction.now()):
        raise UnauthenticatedError
