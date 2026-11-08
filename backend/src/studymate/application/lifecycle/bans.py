"""Explicit ban/unban use case; no SQL, HTTP, restore or recovery authority."""

from dataclasses import dataclass
from uuid import uuid4

from studymate.application.idempotency import IntentFingerprinter
from studymate.application.identity.sessions import SessionHasher
from studymate.application.lifecycle.ban_ports import BanUnitOfWork, LifecycleTargetUnavailableError
from studymate.application.lifecycle.commands import ChangeAccountBanCommand
from studymate.application.lifecycle.intents import LifecycleIntent, resolve_ban_intent
from studymate.application.lifecycle.planning import prepare_ban_change
from studymate.application.operator.authority import finish_operator, require_operator
from studymate.domain.lifecycle.states import BanTransition


@dataclass(frozen=True, slots=True)
class ChangeAccountBan:
    unit_of_work: BanUnitOfWork
    hasher: SessionHasher
    fingerprinter: IntentFingerprinter

    async def __call__(self, command: ChangeAccountBanCommand) -> BanTransition:
        actor_digest = await self.hasher.digest(command.credential)
        async with self.unit_of_work.transaction(actor_digest, command.account_id) as transaction:
            principal = await require_operator(transaction, command.credential, self.hasher)
            actor_id = principal.identity.session.account_id
            fingerprint = await self.fingerprinter.fingerprint(command.fingerprint_parts(actor_id))
            prior = await transaction.prior_lifecycle_intent(
                actor_id, command.operation, command.intent_key
            )
            replay = resolve_ban_intent(prior, command, actor_id, fingerprint)
            if replay is not None:
                await finish_operator(transaction, principal)
                return replay
            state = await transaction.target_lifecycle(command.account_id)
            if state is None:
                raise LifecycleTargetUnavailableError
            at = await transaction.now()
            transition = prepare_ban_change(principal, state, command, uuid4(), at)
            if transition.changed:
                await transaction.apply_ban_transition(transition)
            await transaction.remember_lifecycle_intent(
                LifecycleIntent(
                    actor_id, command.operation, command.intent_key, fingerprint, transition
                ),
                at,
            )
            await finish_operator(transaction, principal)
            return transition
