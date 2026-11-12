import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, MetaData, inspect, select
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.domain.membership import GOOGLE_ISSUER
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.schema import MODELS
from tests.integration.migrations import migrate
from tests.integration.schema_checks import assert_check_constraints_match_metadata

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 7, tzinfo=UTC)


async def test_revision_upgrade_matches_models_and_can_be_reversed(engine: AsyncEngine) -> None:
    def verify_schema(connection: Connection) -> None:
        metadata = MetaData()
        for model in MODELS:
            model.metadata.tables[model.__tablename__].to_metadata(metadata)
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []
        assert_check_constraints_match_metadata(connection, metadata)
        assert set(inspect(connection).get_table_names()) == {
            "client_observation_batches",
            "client_observations",
            "client_observation_frames",
            "external_delivery_destinations",
            "external_delivery_sources",
            "external_deliveries",
            "external_delivery_attempts",
            "external_delivery_schedule",
            "discovery_contexts",
            "discovery_decision_heads",
            "private_passes",
            "private_pass_revisions",
            "private_pass_intents",
            "request_previews",
            "request_disclosures",
            "request_view_acknowledgements",
            "connection_requests",
            "request_revisions",
            "request_send_days",
            "request_command_intents",
            "conversations",
            "chat_image_preparations",
            "chat_image_queue_origins",
            "chat_image_transport_cleanup",
            "chat_image_revisions",
            "chat_image_attempts",
            "chat_image_intents",
            "study_outcomes",
            "study_outcome_revisions",
            "peer_feedback",
            "peer_feedback_revisions",
            "peer_feedback_removals",
            "study_prompt_receipts",
            "feedback_command_intents",
            "change_outbox",
            "change_recipient_heads",
            "published_changes",
            "operator_access",
            "operator_access_revisions",
            "operator_audits",
            "operator_membership_verifications",
            "operator_photo_review_revisions",
            "operator_photo_review_intents",
            "operator_report_review_revisions",
            "operator_report_review_intents",
            "operator_membership_verification_intents",
            "conversation_goal_shares",
            "conversation_goal_share_heads",
            "conversation_goal_share_intents",
            "conversation_read_positions",
            "conversation_read_revisions",
            "conversation_read_intents",
            "message_operations",
            "messages",
            "message_command_intents",
            "accounts",
            "account_lifecycle_revisions",
            "account_lifecycle_intents",
            "account_deletion_workflows",
            "relationships",
            "block_revisions",
            "blocks",
            "block_write_intents",
            "profile_access_contexts",
            "message_report_contexts",
            "bootstrap_catalogue_manifests",
            "notification_preference_revisions",
            "notification_preference_intents",
            "support_proofs",
            "support_preparations",
            "support_cases",
            "support_case_revisions",
            "support_case_intents",
            "support_operator_intents",
            "profile_reports",
            "profile_report_intents",
            "external_identities",
            "sessions",
            "institutional_bindings",
            "alembic_version",
            "login_transactions",
            "login_callback_attempts",
            "email_challenges",
            "email_intents",
            "email_outbox",
            "policy_documents",
            "registration_contexts",
            "registration_receipts",
            "profiles",
            "profile_revisions",
            "profile_languages",
            "profile_write_intents",
            "subjects",
            "subject_aliases",
            "goals",
            "goal_revisions",
            "goal_write_intents",
            "help_profiles",
            "help_revisions",
            "help_selections",
            "help_write_intents",
            "photo_processing_attempts",
            "photo_transport_cleanup",
            "photo_uploads",
            "photo_upload_revisions",
            "photo_revisions",
            "photos",
            "media_write_intents",
            "media_execution_origins",
            "product_events",
            "discovery_freshness_policies",
            "discovery_exposure",
            "ai_jobs",
            "ai_intents",
            "ai_actor_budgets",
            "ai_executor_slot",
            "ai_attempts",
            "profile_activations",
            "visibility_revisions",
            "visibility_write_intents",
        }

    async with engine.begin() as connection:
        await connection.run_sync(migrate, "head")
        await connection.run_sync(verify_schema)
        await connection.run_sync(migrate, "base")
        remaining = await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        assert remaining == ["alembic_version"]
        await connection.run_sync(migrate, "head")
        await connection.run_sync(verify_schema)


async def add_accounts(engine: AsyncEngine) -> tuple[UUID, UUID]:
    identities = (uuid4(), uuid4())
    async with async_sessionmaker(engine).begin() as session:
        session.add_all([AccountRecord(id=identity, created_at=NOW) for identity in identities])
    return identities


async def test_competing_google_identity_is_unique(identity_engine: AsyncEngine) -> None:
    first, second = await add_accounts(identity_engine)

    async def claim(account_id: UUID) -> bool:
        try:
            async with async_sessionmaker(identity_engine).begin() as session:
                session.add(
                    ExternalIdentityRecord(
                        id=uuid4(),
                        account_id=account_id,
                        issuer=GOOGLE_ISSUER,
                        subject="same-subject",
                        created_at=NOW,
                    )
                )
        except IntegrityError:
            return False
        return True

    assert sorted(await asyncio.gather(claim(first), claim(second))) == [False, True]
    async with async_sessionmaker(identity_engine)() as session:
        assert len((await session.scalars(select(ExternalIdentityRecord))).all()) == 1


async def test_competing_membership_binding_is_unique_even_after_revocation(
    identity_engine: AsyncEngine,
) -> None:
    first, second = await add_accounts(identity_engine)

    async def claim(account_id: UUID) -> bool:
        try:
            async with async_sessionmaker(identity_engine).begin() as session:
                session.add(
                    InstitutionalBindingRecord(
                        account_id=account_id,
                        email="tp@mail.apu.edu.my",
                        verified_at=NOW,
                        revoked_at=NOW + timedelta(seconds=1),
                    )
                )
        except IntegrityError:
            return False
        return True

    assert sorted(await asyncio.gather(claim(first), claim(second))) == [False, True]
    async with async_sessionmaker(identity_engine)() as session:
        assert len((await session.scalars(select(InstitutionalBindingRecord))).all()) == 1
        assert (await session.scalars(select(SessionRecord))).all() == []


async def test_identity_transaction_rolls_back_without_partial_account(
    identity_engine: AsyncEngine,
) -> None:
    identity = uuid4()
    sessions = async_sessionmaker(identity_engine)

    async def invalid_transaction() -> None:
        async with sessions.begin() as session:
            session.add(AccountRecord(id=identity, created_at=NOW))
            await session.flush()
            session.add(
                ExternalIdentityRecord(
                    id=uuid4(),
                    account_id=identity,
                    issuer="https://evil.example",
                    subject="subject",
                    created_at=NOW,
                )
            )

    with pytest.raises(IntegrityError):
        await invalid_transaction()
    async with sessions() as session:
        assert await session.get(AccountRecord, identity) is None


@pytest.mark.parametrize(
    "email",
    [
        "TP@mail.apu.edu.my",
        "tp@mail.apu.edu.my.evil.example",
        "tp@sub.mail.apu.edu.my",
        "tp..name@mail.apu.edu.my",
        f"{'a' * 65}@mail.apu.edu.my",
        "\u212a@mail.apu.edu.my",
    ],
)
async def test_database_rejects_noncanonical_student_address(
    identity_engine: AsyncEngine,
    email: str,
) -> None:
    first, _ = await add_accounts(identity_engine)
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(InstitutionalBindingRecord(account_id=first, email=email, verified_at=NOW))


async def test_database_session_requires_hash_and_valid_lifecycle(
    identity_engine: AsyncEngine,
) -> None:
    first, _ = await add_accounts(identity_engine)
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(
                SessionRecord(
                    id=uuid4(),
                    account_id=first,
                    secret_digest=b"plaintext-secret",
                    issued_at=NOW,
                    expires_at=NOW + timedelta(days=7),
                )
            )
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(
                SessionRecord(
                    id=uuid4(),
                    account_id=first,
                    secret_digest=bytes(32),
                    issued_at=NOW,
                    expires_at=NOW,
                )
            )


async def test_check_expression_drift_is_detected_even_when_alembic_misses_it(
    identity_engine: AsyncEngine,
) -> None:
    def verify_same_name_drift(connection: Connection) -> None:
        metadata = MetaData()
        for model in MODELS:
            model.metadata.tables[model.__tablename__].to_metadata(metadata)
        table = metadata.tables["change_recipient_heads"]
        positive_sequence = next(
            constraint
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
            and str(constraint.name).endswith("positive_next_sequence")
        )
        name = positive_sequence.name
        table.constraints.remove(positive_sequence)
        table.append_constraint(CheckConstraint("next_sequence > 1", name=name))
        # Alembic's comparison does not compare CHECK expressions, even with equal names.
        assert compare_metadata(MigrationContext.configure(connection), metadata) == []
        with pytest.raises(AssertionError, match="change_recipient_heads"):
            assert_check_constraints_match_metadata(connection, metadata)

    async with identity_engine.begin() as connection:
        await connection.run_sync(verify_same_name_drift)
