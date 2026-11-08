import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.idempotency import IdempotencyConflictError, IntentKey
from studymate.application.identity.registration import (
    BeginRegistration,
    BeginRegistrationCommand,
    CompleteRegistration,
    CompleteRegistrationCommand,
    PolicyDocumentUnavailableError,
    ReadPolicyStatus,
    ReadPublishedPolicy,
    RegistrationActionDeniedError,
    RegistrationAlreadyCompletedError,
    RegistrationContextUnavailableError,
    RegistrationDocumentsUnavailableError,
    RegistrationSetupIncompleteError,
)
from studymate.application.identity.sessions import SessionCredential, UnauthenticatedError
from studymate.application.profiles.basics import SaveOwnProfile, SaveProfileCommand
from studymate.application.profiles.help_subjects import (
    SaveHelpCommand,
    SaveOwnHelpSubjects,
)
from studymate.domain.profiles import DisplayName, OnboardingTask, ProfileBasics
from studymate.domain.registration import PolicyKind, PolicyVersion
from studymate.domain.study_context import HelpSubject, HelpSubjects
from studymate.infrastructure.persistence.help_subjects import SqlHelpUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    InstitutionalBindingRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.onboarding_models import ProfileActivationRecord
from studymate.infrastructure.persistence.profiles import SqlProfileUnitOfWork
from studymate.infrastructure.persistence.registration import SqlRegistrationUnitOfWork
from studymate.infrastructure.persistence.registration_models import (
    PolicyDocumentRecord,
    RegistrationContextRecord,
    RegistrationReceiptRecord,
)
from studymate.infrastructure.security.intent_fingerprint import HmacIntentFingerprinter
from studymate.infrastructure.security.session_digest import Sha256SessionHasher
from tests.integration.catalogue_fixture import subject
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.registration_fixture import documents

pytestmark = pytest.mark.integration


async def actor(
    engine: AsyncEngine, *, verified: bool = True, account_id: UUID | None = None
) -> tuple[SessionCredential, UUID]:
    now = datetime.now(UTC)
    credential = SessionCredential(uuid4().hex + uuid4().hex[:11])
    async with async_sessionmaker(engine).begin() as session:
        if account_id is None:
            account_id = uuid4()
            session.add(AccountRecord(id=account_id, created_at=now))
            await session.flush()
            if verified:
                session.add(
                    InstitutionalBindingRecord(
                        account_id=account_id,
                        email=f"{account_id.hex}@mail.apu.edu.my",
                        verified_at=now,
                    )
                )
        session.add(
            SessionRecord(
                id=uuid4(),
                account_id=account_id,
                issued_at=now - timedelta(seconds=1),
                expires_at=now + timedelta(days=7),
                secret_digest=await Sha256SessionHasher().digest(credential),
            )
        )
    return credential, account_id


def registration(
    engine: AsyncEngine,
) -> tuple[BeginRegistration, CompleteRegistration, ReadPolicyStatus]:
    uow = SqlRegistrationUnitOfWork(async_sessionmaker(engine, expire_on_commit=False))
    hasher = Sha256SessionHasher()
    return (
        BeginRegistration(uow, hasher),
        CompleteRegistration(uow, hasher),
        ReadPolicyStatus(uow, hasher),
    )


async def test_registration_requires_real_issued_context_and_is_recorded_once(
    identity_engine: AsyncEngine,
) -> None:
    credential, account_id = await actor(identity_engine)
    await documents(identity_engine)
    begin, complete, status = registration(identity_engine)
    assert (await status(credential)).receipt is None
    with pytest.raises(RegistrationContextUnavailableError):
        await complete(CompleteRegistrationCommand(credential, uuid4(), IntentKey(str(uuid4()))))
    begin_command = BeginRegistrationCommand(credential, IntentKey(str(uuid4())))
    context = await begin(begin_command)
    assert await begin(begin_command) == context
    assert (await status(credential)).receipt is None
    command = CompleteRegistrationCommand(credential, context.id, IntentKey(str(uuid4())))
    await ready_setup(identity_engine, credential)
    first, replay = await asyncio.gather(complete(command), complete(command))
    assert replay == first
    assert first.account_id == account_id
    assert first.context.notice_text == context.notice_text
    assert first.registered_at == first.context.completed_at
    assert (await status(credential)).receipt == first
    assert await complete(replace(command, intent_key=IntentKey(str(uuid4())))) == first
    with pytest.raises(IdempotencyConflictError):
        await complete(replace(command, context_id=uuid4()))
    with pytest.raises(RegistrationAlreadyCompletedError):
        await begin(BeginRegistrationCommand(credential, IntentKey(str(uuid4()))))
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(RegistrationReceiptRecord))
        ).one() == 1


async def test_missing_documents_do_not_create_fictitious_policy_receipt(
    identity_engine: AsyncEngine,
) -> None:
    credential, _ = await actor(identity_engine)
    begin, _, status = registration(identity_engine)
    with pytest.raises(RegistrationDocumentsUnavailableError):
        await begin(BeginRegistrationCommand(credential, IntentKey(str(uuid4()))))
    result = await status(credential)
    assert result.receipt is None
    assert result.current_terms is None
    assert result.current_privacy is None


async def test_publication_changes_never_rewrite_original_registration(
    identity_engine: AsyncEngine,
) -> None:
    credential, _ = await actor(identity_engine)
    await documents(identity_engine)
    begin, complete, status = registration(identity_engine)
    context = await begin(BeginRegistrationCommand(credential, IntentKey(str(uuid4()))))
    await documents(identity_engine, "synthetic-test-v2")
    await ready_setup(identity_engine, credential)
    receipt = await complete(
        CompleteRegistrationCommand(credential, context.id, IntentKey(str(uuid4())))
    )
    result = await status(credential)
    assert result.receipt == receipt
    assert receipt.context.terms.version == PolicyVersion("synthetic-test-v1")
    assert result.current_terms is not None
    assert result.current_terms.version == PolicyVersion("synthetic-test-v2")
    later_session, _ = await actor(identity_engine, account_id=receipt.account_id)
    assert (await status(later_session)).receipt == receipt
    async with async_sessionmaker(identity_engine)() as session:
        assert (
            await session.scalars(select(func.count()).select_from(RegistrationReceiptRecord))
        ).one() == 1


async def test_registration_context_cannot_cross_accounts_sessions_or_deadline(
    identity_engine: AsyncEngine,
) -> None:
    credential, account_id = await actor(identity_engine)
    other, _ = await actor(identity_engine)
    alternate, _ = await actor(identity_engine, account_id=account_id)
    await documents(identity_engine)
    begin, complete, _ = registration(identity_engine)
    command = BeginRegistrationCommand(credential, IntentKey(str(uuid4())))
    context = await begin(command)
    with pytest.raises(IdempotencyConflictError):
        await begin(replace(command, credential=alternate))
    for wrong_actor in (other, alternate):
        with pytest.raises(RegistrationContextUnavailableError):
            await complete(
                CompleteRegistrationCommand(wrong_actor, context.id, IntentKey(str(uuid4())))
            )
    async with async_sessionmaker(identity_engine).begin() as session:
        await session.execute(
            update(RegistrationContextRecord)
            .where(RegistrationContextRecord.id == context.id)
            .values(
                created_at=func.clock_timestamp() - timedelta(minutes=11),
                expires_at=func.clock_timestamp() - timedelta(seconds=1),
            )
        )
    with pytest.raises(RegistrationContextUnavailableError):
        await complete(CompleteRegistrationCommand(credential, context.id, IntentKey(str(uuid4()))))


@pytest.mark.parametrize("state", ["unverified", "banned", "deleted"])
async def test_registration_honours_verification_and_lifecycle(
    identity_engine: AsyncEngine, state: str
) -> None:
    credential, account_id = await actor(identity_engine, verified=state != "unverified")
    await documents(identity_engine)
    if state != "unverified":
        async with async_sessionmaker(identity_engine).begin() as session:
            field = AccountRecord.banned_at if state == "banned" else AccountRecord.deleted_at
            await session.execute(
                update(AccountRecord)
                .where(AccountRecord.id == account_id)
                .values({field: func.clock_timestamp()})
            )
    begin, _, status = registration(identity_engine)
    error = UnauthenticatedError if state == "deleted" else RegistrationActionDeniedError
    with pytest.raises(error):
        await begin(BeginRegistrationCommand(credential, IntentKey(str(uuid4()))))
    if state == "banned":
        assert (await status(credential)).current_terms is not None


async def test_public_policy_read_returns_real_published_versions_only(
    identity_engine: AsyncEngine,
) -> None:
    read = ReadPublishedPolicy(SqlRegistrationUnitOfWork(async_sessionmaker(identity_engine)))
    with pytest.raises(PolicyDocumentUnavailableError):
        await read(PolicyKind.TERMS)
    await documents(identity_engine)
    first = await read(PolicyKind.TERMS)
    assert first.reference.version == PolicyVersion("synthetic-test-v1")
    assert first.content.startswith("Synthetic test")
    await documents(identity_engine, "synthetic-test-v2")
    assert (await read(PolicyKind.TERMS, PolicyVersion("synthetic-test-v1"))) == first
    assert (await read(PolicyKind.TERMS)).reference.version == PolicyVersion("synthetic-test-v2")
    async with async_sessionmaker(identity_engine).begin() as session:
        session.add(
            PolicyDocumentRecord(
                id=uuid4(),
                kind="terms",
                version="synthetic-future",
                title="Synthetic future",
                content="Synthetic future test body.",
                published_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
    with pytest.raises(PolicyDocumentUnavailableError):
        await read(PolicyKind.TERMS, PolicyVersion("synthetic-future"))


async def test_database_cannot_record_receipt_without_actual_completion(
    identity_engine: AsyncEngine,
) -> None:
    credential, account_id = await actor(identity_engine)
    await documents(identity_engine)
    begin, _, _ = registration(identity_engine)
    context = await begin(BeginRegistrationCommand(credential, IntentKey(str(uuid4()))))
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            session.add(
                RegistrationReceiptRecord(
                    id=uuid4(),
                    account_id=account_id,
                    context_id=context.id,
                    registered_at=datetime.now(UTC),
                    intent_key="synthetic-invalid-receipt",
                )
            )


async def test_database_cannot_label_privacy_document_as_terms(
    identity_engine: AsyncEngine,
) -> None:
    credential, _ = await actor(identity_engine)
    await documents(identity_engine)
    begin, _, _ = registration(identity_engine)
    context = await begin(BeginRegistrationCommand(credential, IntentKey(str(uuid4()))))
    with pytest.raises(IntegrityError):
        async with async_sessionmaker(identity_engine).begin() as session:
            await session.execute(
                update(RegistrationContextRecord)
                .where(RegistrationContextRecord.id == context.id)
                .values(terms_id=context.privacy.id)
            )


async def test_incomplete_setup_rolls_back_receipt_and_context_then_same_intent_can_complete(
    identity_engine: AsyncEngine,
) -> None:
    credential, account_id = await actor(identity_engine)
    await documents(identity_engine)
    begin, complete, status = registration(identity_engine)
    context = await begin(BeginRegistrationCommand(credential, IntentKey(str(uuid4()))))
    command = CompleteRegistrationCommand(credential, context.id, IntentKey(str(uuid4())))
    with pytest.raises(RegistrationSetupIncompleteError) as failure:
        await complete(command)
    assert tuple(item.value for item in failure.value.requirements) == (
        "display_name",
        "photo",
        "study_goal",
    )
    assert (await status(credential)).receipt is None
    async with async_sessionmaker(identity_engine)() as session:
        stored_context = await session.get(RegistrationContextRecord, context.id)
        assert stored_context is not None
        assert stored_context.completed_at is None
        assert await session.get(ProfileActivationRecord, account_id) is None
    await ready_setup(identity_engine, credential)
    receipt = await complete(command)
    async with async_sessionmaker(identity_engine)() as session:
        activation = await session.get(ProfileActivationRecord, account_id)
        assert activation is not None
        assert activation.registration_id == receipt.id
        assert activation.profile_version == 1
        assert activation.photo_version == 1
        assert activation.goal_id is not None
        assert activation.help_version is None
    assert await complete(command) == receipt


async def test_helper_task_requires_actual_help_selection_even_with_existing_goal(
    identity_engine: AsyncEngine,
) -> None:
    credential, account_id = await actor(identity_engine)
    await ready_setup(identity_engine, credential)
    await documents(identity_engine)
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    hasher = Sha256SessionHasher()
    fingerprint = HmacIntentFingerprinter(bytes(range(32)))
    await SaveOwnProfile(SqlProfileUnitOfWork(sessions), hasher, fingerprint)(
        SaveProfileCommand(
            credential,
            ProfileBasics(DisplayName("Synthetic helper")),
            OnboardingTask.OFFER_HELP,
            1,
            IntentKey(str(uuid4())),
        )
    )
    begin, complete, _ = registration(identity_engine)
    context = await begin(BeginRegistrationCommand(credential, IntentKey(str(uuid4()))))
    command = CompleteRegistrationCommand(credential, context.id, IntentKey(str(uuid4())))
    with pytest.raises(RegistrationSetupIncompleteError) as missing:
        await complete(command)
    assert tuple(item.value for item in missing.value.requirements) == ("help_subjects",)
    canonical = await subject(identity_engine)
    await SaveOwnHelpSubjects(SqlHelpUnitOfWork(sessions), hasher, fingerprint)(
        SaveHelpCommand(
            credential, HelpSubjects((HelpSubject(canonical.id),)), 0, IntentKey(str(uuid4()))
        )
    )
    await complete(command)
    async with sessions() as session:
        activation = await session.get(ProfileActivationRecord, account_id)
        assert activation is not None
        assert activation.help_version == 1
        assert activation.profile_version == 1 + 1
