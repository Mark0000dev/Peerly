from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from studymate.application.identity.sessions import ReadIdentity, SessionCredential
from studymate.domain.membership import IdentityCapabilities, identity_capabilities
from studymate.domain.registration import RegistrationReceipt


@dataclass(frozen=True, slots=True)
class IdentityBootstrap:
    account_id: UUID
    account_status: Literal["active", "banned"]
    membership_status: Literal["unverified", "verified", "revoked"]
    verified_at: datetime | None
    capabilities: IdentityCapabilities
    registration: RegistrationReceipt | None
    email_challenge_id: UUID | None


@dataclass(frozen=True, slots=True)
class ReadBootstrap:
    identity: ReadIdentity

    async def __call__(self, credential: SessionCredential) -> IdentityBootstrap:
        actor = await self.identity(credential)
        membership = actor.membership
        return IdentityBootstrap(
            account_id=actor.session.account_id,
            registration=actor.registration,
            email_challenge_id=actor.email_challenge_id,
            account_status="banned" if actor.banned else "active",
            membership_status=("verified" if membership.is_verified else "revoked")
            if membership
            else "unverified",
            verified_at=membership.verified_at if membership else None,
            capabilities=identity_capabilities(
                membership=membership,
                banned=actor.banned,
                activation_complete=actor.activation_complete,
            ),
        )
