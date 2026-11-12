"""Actual-authority fake; one transaction rolls back source/receipt/binding effects."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

from studymate.application.idempotency import IntentKey
from studymate.application.operator.membership_verification_ports import ManualMembershipIntent
from studymate.domain.identity import StudentEmail
from studymate.domain.operator.membership_verification import (
    ManualMembershipVerification,
    ManualVerificationTarget,
    SubmittedInstitutionalEmail,
)
from tests.unit.identity_store import NOW
from tests.unit.operator.store import TARGET, Store

CHALLENGE_ID = UUID(int=1101)
GOOGLE_ID = UUID(int=1102)
EMAIL = StudentEmail("synthetic-review@mail.apu.edu.my")


class ManualVerificationStore(Store):
    def __init__(self) -> None:
        super().__init__()
        self.target: ManualVerificationTarget | None = ManualVerificationTarget(
            TARGET,
            GOOGLE_ID,
            False,
            False,
            False,
            False,
            SubmittedInstitutionalEmail(
                CHALLENGE_ID, TARGET, EMAIL, NOW - timedelta(days=1), NOW - timedelta(hours=1)
            ),
        )
        self.intents: dict[tuple[UUID, str], ManualMembershipIntent] = {}
        self.sources: list[ManualMembershipVerification] = []
        self.claim_conflict = False
        self.fail_commit = False

    @asynccontextmanager
    async def transaction(
        self, actor_secret_digest: bytes | None = None, target_account_id: UUID | None = None
    ) -> AsyncIterator["ManualVerificationStore"]:
        if actor_secret_digest is not None:
            assert actor_secret_digest
            assert target_account_id == TARGET
        else:
            assert target_account_id is None
        before = (self.target, self.intents.copy(), self.sources.copy())
        try:
            async with super().transaction():
                yield self
                if self.fail_commit:
                    raise RuntimeError("synthetic commit failure")
        except BaseException:
            self.target, self.intents, self.sources = before
            raise

    async def verification_target(self, account_id: UUID) -> ManualVerificationTarget | None:
        self.queried()
        assert account_id == TARGET
        return self.target

    async def prior_manual_verification(
        self, operator_id: UUID, key: IntentKey
    ) -> ManualMembershipIntent | None:
        return self.intents.get((operator_id, key.value))

    async def apply_manual_verification(
        self,
        source: ManualMembershipVerification,
        email: StudentEmail,
        key: IntentKey,
        fingerprint: bytes,
    ) -> bool:
        assert self.target is not None
        assert self.target.latest is not None
        assert source.operator == self.access
        assert source.actor_session_id == self.actor.session.id
        assert email == self.target.latest.email
        if self.claim_conflict:
            return False
        self.sources.append(source)
        self.intents[(source.operator.account_id, key.value)] = ManualMembershipIntent(
            fingerprint, source
        )
        self.target = replace(
            self.target,
            has_binding=True,
            latest=replace(self.target.latest, superseded_at=source.verified_at),
            manual_source=source,
        )
        if self.expire_after_audit:
            self.clock = self.actor.session.expires_at
        return True
