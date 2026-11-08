"""Pure lifecycle planning against already authenticated, locked identity/operator sources.

These helpers do not authenticate credentials, authorize a workflow or persist mutations.
Main transaction usecases must use the actual shared session/operator guard and actual
recent-Google/preflight authorization before applying any returned source.
"""

from datetime import datetime
from uuid import UUID

from studymate.application.identity.sessions import IdentitySnapshot, UnauthenticatedError
from studymate.application.lifecycle.commands import ChangeAccountBanCommand
from studymate.application.operator.authority import OperatorAccessDeniedError, OperatorPrincipal
from studymate.domain.lifecycle.states import (
    AccountLifecycle,
    BanChangeEvidence,
    BanTransition,
    plan_ban_change,
)


def prepare_ban_change(
    principal: OperatorPrincipal,
    state: AccountLifecycle,
    command: ChangeAccountBanCommand,
    change_id: UUID,
    at: datetime,
) -> BanTransition:
    """Principal must come from require_operator(command.credential) in the same locked TX."""
    identity = principal.identity
    if identity.deleted_at is not None or not identity.session.is_active(at):
        raise UnauthenticatedError
    if identity.banned or not principal.access.is_active(at):
        raise OperatorAccessDeniedError
    if principal.access.account_id != identity.session.account_id:
        raise RuntimeError("Lifecycle operator source belongs to another actual session account")
    if state.account_id != command.account_id:
        raise RuntimeError("Lifecycle target source belongs to another requested account")
    return plan_ban_change(
        state,
        banned=command.banned,
        evidence=BanChangeEvidence(change_id, at, principal.access, identity.session.id),
        reason=command.reason,
    )


def require_self_deletion_lifecycle(
    identity: IdentitySnapshot, state: AccountLifecycle, at: datetime
) -> None:
    """Lifecycle slice only, NOT recent Google/workflow authorization or a mutation port.

    Ban intentionally does not remove limited self account-management permission.
    Membership, registration and activation are not prerequisites for deleting an account.
    """
    if state.account_id != identity.session.account_id:
        raise RuntimeError("Self-deletion target differs from its actual session account")
    if (
        identity.deleted_at is not None
        or state.deleted_at is not None
        or not identity.session.is_active(at)
    ):
        raise UnauthenticatedError


def check_submission_session_deadline(identity: IdentitySnapshot, at: datetime) -> None:
    """Recheck the original submitting session before commit, including self revocation.

    Deletion intentionally revokes sessions inside its transaction; main retains the
    original locked submission snapshot for its expiry check, not a new login authority.
    """
    if not identity.session.is_active(at):
        raise UnauthenticatedError
