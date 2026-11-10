from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import insert, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.membership import GOOGLE_ISSUER
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
)
from tests.integration.identity_recreation.fixtures import (
    EMAIL,
    deleted_claims,
    fresh_account,
    google_claim,
)
from tests.integration.migrations import migrate

pytestmark = pytest.mark.integration
UPGRADE_FROM_REVISION = "0052_student_support"
DOWNGRADE_TO_REVISION = "0053_operator_support_search"


def downgrade_to_previous(connection: Connection) -> None:
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    command.downgrade(config, DOWNGRADE_TO_REVISION)


async def test_upgrade_retires_deleted_claims_and_preserves_original_identifiers(
    engine: AsyncEngine,
) -> None:
    deleted, live = uuid4(), uuid4()
    external_ids = (uuid4(), uuid4())
    at = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.run_sync(migrate, UPGRADE_FROM_REVISION)
        # Actual deployed head52 sources upgrade through53 and54; future columns are omitted.
        await connection.execute(
            insert(AccountRecord),
            [
                {"id": deleted, "created_at": at, "deleted_at": at},
                {"id": live, "created_at": at, "deleted_at": None},
            ],
        )
        await connection.execute(
            insert(ExternalIdentityRecord),
            [
                {
                    "id": external_ids[0],
                    "account_id": deleted,
                    "issuer": GOOGLE_ISSUER,
                    "subject": "deleted-google-subject",
                    "created_at": at,
                },
                {
                    "id": external_ids[1],
                    "account_id": live,
                    "issuer": GOOGLE_ISSUER,
                    "subject": "live-google-subject",
                    "created_at": at,
                },
            ],
        )
        await connection.execute(
            insert(InstitutionalBindingRecord),
            [
                {"account_id": deleted, "email": EMAIL, "verified_at": at, "revoked_at": None},
                {
                    "account_id": live,
                    "email": "revoked-reserved@mail.apu.edu.my",
                    "verified_at": at,
                    "revoked_at": at,
                },
            ],
        )
    # Existing deployment data is committed before the migration transaction starts.
    async with engine.begin() as connection:
        await connection.run_sync(migrate, "head")
    async with async_sessionmaker(engine)() as session:
        old_identity = await session.get(ExternalIdentityRecord, external_ids[0])
        old_mail = await session.get(InstitutionalBindingRecord, deleted)
        live_identity = await session.get(ExternalIdentityRecord, external_ids[1])
        live_mail = await session.get(InstitutionalBindingRecord, live)
        assert old_identity is not None
        assert old_mail is not None
        assert live_identity is not None
        assert live_mail is not None
        assert old_identity.retired_at == at
        assert old_mail.retired_at == at
        assert old_identity.subject == "deleted-google-subject"
        assert old_identity.issuer == GOOGLE_ISSUER
        assert old_identity.account_id == deleted
        assert old_mail.email == EMAIL
        assert old_mail.account_id == deleted
        assert live_identity.retired_at is None
        assert live_mail.retired_at is None
        assert live_mail.revoked_at == at


@pytest.mark.parametrize("duplicate", ["google", "mailbox"])
async def test_downgrade_refuses_duplicate_historical_claims_and_preserves_both_lineages(
    identity_engine: AsyncEngine, duplicate: str
) -> None:
    old = await deleted_claims(identity_engine)
    owner = await fresh_account(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    async with sessions.begin() as session:
        if duplicate == "google":
            session.add(google_claim(owner, old.subject, old.retired_at))
        else:
            session.add(
                InstitutionalBindingRecord(
                    account_id=owner, email=EMAIL, verified_at=old.retired_at, retired_at=None
                )
            )
    with pytest.raises(RuntimeError, match=r"retained|duplicate|history|claim"):
        async with identity_engine.begin() as connection:
            await connection.run_sync(downgrade_to_previous)
    async with sessions() as session:
        original = await session.get(ExternalIdentityRecord, old.identity_id)
        assert original is not None
        assert original.retired_at == old.retired_at
        historical_mail = await session.get(InstitutionalBindingRecord, old.account_id)
        assert historical_mail is not None
        assert historical_mail.email == EMAIL
        if duplicate == "google":
            recreated = (
                await session.scalars(
                    select(ExternalIdentityRecord).where(ExternalIdentityRecord.account_id == owner)
                )
            ).one()
            assert recreated.subject == old.subject
            assert recreated.retired_at is None
        else:
            recreated_mail = await session.get(InstitutionalBindingRecord, owner)
            assert recreated_mail is not None
            assert recreated_mail.email == EMAIL
            assert recreated_mail.retired_at is None
