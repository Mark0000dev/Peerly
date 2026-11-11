from datetime import UTC, datetime, timedelta
from uuid import UUID

from studymate.application.identity.sessions import IdentitySnapshot, SessionCredential
from studymate.domain.identity import Session, StudentEmail
from studymate.domain.membership import Membership
from studymate.infrastructure.security.session_digest import Sha256SessionHasher

NOW = datetime(2026, 11, 7, tzinfo=UTC)
CREDENTIAL = SessionCredential("a" * 43)


class IdentityStore:
    def __init__(self) -> None:
        self.actor = IdentitySnapshot(
            Session(UUID(int=1), UUID(int=2), NOW - timedelta(minutes=1), NOW + timedelta(hours=1)),
            Membership(StudentEmail("synthetic@mail.apu.edu.my"), NOW),
            False,
        )
        self.clock = NOW

    def authenticated(self, account_id: UUID) -> None:
        assert account_id == self.actor.session.account_id

    async def lock_identity(self, secret_digest: bytes) -> IdentitySnapshot | None:
        assert secret_digest == await Sha256SessionHasher().digest(CREDENTIAL)
        return self.actor

    async def now(self) -> datetime:
        return self.clock
