from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.sessions import SessionCredential
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.security.session_digest import Sha256SessionHasher


@dataclass(frozen=True, slots=True)
class Actor:
    id: UUID
    credential: SessionCredential


async def actor(engine: AsyncEngine, *, verified: bool = True) -> Actor:
    owner = Actor(uuid4(), SessionCredential(uuid4().hex + uuid4().hex[:11]))
    async with async_sessionmaker(engine).begin() as session:
        now = await session.scalar(select(func.clock_timestamp()))
        assert isinstance(now, datetime)
        # Minimal historical account seed: later nullable lifecycle fields must
        # not be emitted while migration tests intentionally exercise old heads.
        await session.execute(insert(AccountRecord).values(id=owner.id, created_at=now))
        session.add(
            SessionRecord(
                id=uuid4(),
                account_id=owner.id,
                secret_digest=await Sha256SessionHasher().digest(owner.credential),
                issued_at=now - timedelta(minutes=1),
                expires_at=now + timedelta(days=7),
            )
        )
        if verified:
            session.add(
                InstitutionalBindingRecord(
                    account_id=owner.id,
                    email=f"synthetic-{owner.id.hex}@mail.apu.edu.my",
                    verified_at=now,
                )
            )
    return owner
