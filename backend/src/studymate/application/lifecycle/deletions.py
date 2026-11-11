"""Owned workflow deletion and committed-result replay, with no public recovery lookup."""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import (
    IdentitySnapshot,
    SessionHasher,
    UnauthenticatedError,
    require_session_identity,
)
from studymate.application.lifecycle.ban_ports import LifecycleTargetUnavailableError
from studymate.application.lifecycle.commands import DeleteOwnAccountCommand
from studymate.application.lifecycle.deletion_ports import (
    DeletionUnitOfWork,
    DeletionWorkflowAuthorization,
    DeletionWorkflowUnavailableError,
)
from studymate.application.lifecycle.intents import LifecycleIntent, resolve_deletion_intent
from studymate.application.lifecycle.planning import (
    check_submission_session_deadline,
    require_self_deletion_lifecycle,
)
from studymate.domain.lifecycle.states import DeletionTransition, plan_deletion


def require_owned_workflow(
    authorization: DeletionWorkflowAuthorization | None,
    identity: IdentitySnapshot,
    command: DeleteOwnAccountCommand,
    at: datetime,
) -> DeletionWorkflowAuthorization:
    if authorization is None or not authorization.is_valid(at):
        raise DeletionWorkflowUnavailableError
    if (authorization.id, authorization.account_id, authorization.session_id) != (
        command.workflow_id,
        identity.session.account_id,
        identity.session.id,
    ):
        raise RuntimeError(
            "Deletion authorization source differs from actual account/session/workflow"
        )
    return authorization


def check_workflow_deadline(authorization: DeletionWorkflowAuthorization, at: datetime) -> None:
    if not authorization.is_valid(at):
        raise DeletionWorkflowUnavailableError


def check_receipt_deadline(
    authorization: DeletionWorkflowAuthorization,
    identity: IdentitySnapshot,
    at: datetime,
) -> None:
    """Original-credential receipt is bounded by BOTH fixed expiries, ignoring revocation."""
    check_workflow_deadline(authorization, at)
    if at >= identity.session.expires_at:
        raise UnauthenticatedError


@dataclass(frozen=True, slots=True)
class DeleteOwnAccount:
    unit_of_work: DeletionUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: DeleteOwnAccountCommand) -> DeletionTransition:
        digest = await self.hasher.digest(command.credential)
        async with self.unit_of_work.transaction(digest, command.workflow_id) as transaction:
            original = await transaction.lock_identity(digest)
            if original is None:
                raise UnauthenticatedError
            authorization = require_owned_workflow(
                await transaction.authorized_deletion_workflow(digest, command.workflow_id),
                original,
                command,
                await transaction.now(),
            )
            actor_id = original.session.account_id
            fingerprint = await self.fingerprinter.fingerprint(
                command.fingerprint_parts(actor_id, original.session.id)
            )
            prior = await transaction.prior_lifecycle_intent(
                actor_id, command.operation, command.intent_key
            )
            replay = resolve_deletion_intent(prior, command, original, fingerprint)
            if replay is not None:
                # Main's narrow valid workflow proof authorizes this committed receipt only.
                # The original revoked session is deliberately NOT a new live-session grant.
                check_receipt_deadline(authorization, original, await transaction.now())
                return replay
            identity, _ = await require_session_identity(transaction, digest)
            if (identity.session.id, identity.session.account_id) != (
                original.session.id,
                actor_id,
            ):
                raise RuntimeError(
                    "Deletion identity changed from its actual locked original session"
                )
            state = await transaction.target_lifecycle(actor_id)
            if state is None:
                raise LifecycleTargetUnavailableError
            at = await transaction.now()
            require_self_deletion_lifecycle(identity, state, at)
            check_workflow_deadline(authorization, at)
            transition = plan_deletion(
                state,
                change_id=uuid4(),
                at=at,
                actor_session_id=identity.session.id,
                workflow_id=authorization.id,
            )
            await transaction.apply_deletion_transition(transition)
            await transaction.remember_lifecycle_intent(
                LifecycleIntent(
                    actor_id, command.operation, command.intent_key, fingerprint, transition
                ),
                at,
            )
            final_at = await transaction.now()
            check_submission_session_deadline(identity, final_at)
            check_workflow_deadline(authorization, final_at)
            return transition
