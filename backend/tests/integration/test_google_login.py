import asyncio
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.google import (
    GoogleAuthorization,
    GoogleCode,
    GoogleRejectedError,
    GoogleUnavailableError,
)
from studymate.application.identity.login import (
    MAX_STARTS_PER_HOUR,
    AccountUnavailableError,
    BeginGoogleLogin,
    CompleteGoogleLogin,
    LoginRateLimitedError,
)
from studymate.application.identity.sessions import (
    ReadIdentity,
    SessionCredential,
    UnauthenticatedError,
)
from studymate.domain.membership import GOOGLE_ISSUER, GoogleIdentity
from studymate.infrastructure.persistence.google_login import SqlLoginUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    LoginFlowRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.identity_sessions import SqlIdentityUnitOfWork
from studymate.infrastructure.security.login_vault import AeadLoginVault
from studymate.infrastructure.security.session_digest import Sha256SessionHasher

pytestmark = pytest.mark.integration
SOURCE = bytes(32)


class GoogleProviderDouble:
    def __init__(self, subject: str = "same-subject") -> None:
        self.subject = subject
        self.calls = 0
        self.failure: GoogleUnavailableError | None = None

    async def authorization_url(self, authorization: GoogleAuthorization) -> str:
        return "https://accounts.google.com/?state=" + authorization.state

    async def exchange(
        self, code: GoogleCode, authorization: GoogleAuthorization
    ) -> GoogleIdentity:
        assert code.value == "code"
        assert authorization.nonce
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return GoogleIdentity(GOOGLE_ISSUER, self.subject)


def state_from(url: str) -> str:
    return parse_qs(urlsplit(url).query)["state"][0]


def vault() -> AeadLoginVault:
    return AeadLoginVault(bytes(range(32)))


async def test_new_and_returning_google_logins_resolve_one_account(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlLoginUnitOfWork(sessions)
    provider = GoogleProviderDouble()
    begin = BeginGoogleLogin(uow, provider, vault())
    complete = CompleteGoogleLogin(uow, provider, vault())
    first = await begin(return_to="/onboarding", source_digest=SOURCE)
    signed_in = await complete(
        state=state_from(first.redirect_url), browser=first.browser, code=GoogleCode("code")
    )
    reader = ReadIdentity(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher())
    account = await reader(signed_in.credential)
    assert account.membership is None
    assert signed_in.return_to == "/onboarding"
    second = await begin(return_to="/", source_digest=SOURCE)
    signed_in_again = await complete(
        state=state_from(second.redirect_url),
        browser=second.browser,
        code=GoogleCode("code"),
        previous=signed_in.credential,
    )
    assert (
        await reader(signed_in_again.credential)
    ).session.account_id == account.session.account_id
    assert signed_in_again.credential != signed_in.credential
    with pytest.raises(UnauthenticatedError):
        await reader(signed_in.credential)
    async with sessions() as session:
        assert (await session.scalars(select(func.count()).select_from(AccountRecord))).one() == 1
        assert (
            await session.scalars(select(func.count()).select_from(ExternalIdentityRecord))
        ).one() == 1
        flows = (await session.scalars(select(LoginFlowRecord))).all()
        assert all(flow.sealed_material is None and flow.completed_at is not None for flow in flows)


async def test_same_flow_cannot_create_two_sessions_even_concurrently(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlLoginUnitOfWork(sessions)
    provider = GoogleProviderDouble()
    started = await BeginGoogleLogin(uow, provider, vault())(return_to="/", source_digest=SOURCE)
    complete = CompleteGoogleLogin(uow, provider, vault())

    async def callback() -> bool:
        try:
            await complete(
                state=state_from(started.redirect_url),
                browser=started.browser,
                code=GoogleCode("code"),
            )
        except GoogleRejectedError:
            return False
        return True

    assert sorted(await asyncio.gather(callback(), callback())) == [False, True]
    assert provider.calls == 1
    async with sessions() as session:
        assert (await session.scalars(select(func.count()).select_from(SessionRecord))).one() == 1


async def test_concurrent_distinct_flows_for_subject_create_one_account(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlLoginUnitOfWork(sessions)
    provider = GoogleProviderDouble()
    begin = BeginGoogleLogin(uow, provider, vault())
    first = await begin(return_to="/", source_digest=SOURCE)
    second = await begin(return_to="/", source_digest=SOURCE)
    complete = CompleteGoogleLogin(uow, provider, vault())
    results = await asyncio.gather(
        *(
            complete(
                state=state_from(started.redirect_url),
                browser=started.browser,
                code=GoogleCode("code"),
            )
            for started in (first, second)
        )
    )
    reader = ReadIdentity(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher())
    accounts = [await reader(result.credential) for result in results]
    assert accounts[0].session.account_id == accounts[1].session.account_id
    async with sessions() as session:
        assert (await session.scalars(select(func.count()).select_from(AccountRecord))).one() == 1


async def test_distinct_subjects_do_not_merge(identity_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlLoginUnitOfWork(sessions)
    accounts = []
    reader = ReadIdentity(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher())
    for subject in ("first", "second"):
        provider = GoogleProviderDouble(subject)
        started = await BeginGoogleLogin(uow, provider, vault())(
            return_to="/", source_digest=SOURCE
        )
        result = await CompleteGoogleLogin(uow, provider, vault())(
            state=state_from(started.redirect_url),
            browser=started.browser,
            code=GoogleCode("code"),
        )
        accounts.append((await reader(result.credential)).session.account_id)
    assert accounts[0] != accounts[1]


async def test_wrong_browser_and_missing_state_do_not_consume_flow(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlLoginUnitOfWork(sessions)
    provider = GoogleProviderDouble()
    started = await BeginGoogleLogin(uow, provider, vault())(return_to="/", source_digest=SOURCE)
    complete = CompleteGoogleLogin(uow, provider, vault())
    with pytest.raises(GoogleRejectedError):
        await complete(
            state=state_from(started.redirect_url),
            browser=SessionCredential("x" * 43),
            code=GoogleCode("code"),
        )
    with pytest.raises(GoogleRejectedError):
        await complete(state="missing", browser=started.browser, code=GoogleCode("code"))
    await complete(
        state=state_from(started.redirect_url), browser=started.browser, code=GoogleCode("code")
    )
    assert provider.calls == 1


async def test_provider_failure_consumes_flow_and_erases_secrets(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlLoginUnitOfWork(sessions)
    provider = GoogleProviderDouble()
    started = await BeginGoogleLogin(uow, provider, vault())(return_to="/", source_digest=SOURCE)
    provider.failure = GoogleUnavailableError()
    complete = CompleteGoogleLogin(uow, provider, vault())
    with pytest.raises(GoogleUnavailableError):
        await complete(
            state=state_from(started.redirect_url), browser=started.browser, code=GoogleCode("code")
        )
    with pytest.raises(GoogleRejectedError):
        await complete(
            state=state_from(started.redirect_url), browser=started.browser, code=GoogleCode("code")
        )
    async with sessions() as session:
        flow = (await session.scalars(select(LoginFlowRecord))).one()
        assert flow.consumed_at is not None
        assert flow.sealed_material is None
        assert flow.completed_at is None
        assert (await session.scalars(select(func.count()).select_from(SessionRecord))).one() == 0


async def test_cancelled_provider_consent_consumes_flow_without_exchange(
    identity_engine: AsyncEngine,
) -> None:
    uow = SqlLoginUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))
    provider = GoogleProviderDouble()
    started = await BeginGoogleLogin(uow, provider, vault())(return_to="/", source_digest=SOURCE)
    with pytest.raises(GoogleRejectedError):
        await CompleteGoogleLogin(uow, provider, vault())(
            state=state_from(started.redirect_url), browser=started.browser, code=None
        )
    assert provider.calls == 0


@pytest.mark.parametrize(
    "route", ["https://evil.example", "//evil.example", "/onboarding?x=1", "/other"]
)
async def test_return_route_is_allowlisted_before_storage(
    identity_engine: AsyncEngine, route: str
) -> None:
    uow = SqlLoginUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))
    with pytest.raises(GoogleRejectedError):
        await BeginGoogleLogin(uow, GoogleProviderDouble(), vault())(
            return_to=route, source_digest=SOURCE
        )


async def test_google_start_quota_is_persistent_and_atomic(identity_engine: AsyncEngine) -> None:
    uow = SqlLoginUnitOfWork(async_sessionmaker(identity_engine, expire_on_commit=False))
    begin = BeginGoogleLogin(uow, GoogleProviderDouble(), vault())
    for _ in range(MAX_STARTS_PER_HOUR - 1):
        await begin(return_to="/", source_digest=SOURCE)

    async def start() -> bool:
        try:
            await begin(return_to="/", source_digest=SOURCE)
        except LoginRateLimitedError:
            return False
        return True

    assert sorted(await asyncio.gather(start(), start())) == [False, True]


async def test_expired_flow_never_contacts_google(identity_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlLoginUnitOfWork(sessions)
    provider = GoogleProviderDouble()
    started = await BeginGoogleLogin(uow, provider, vault())(return_to="/", source_digest=SOURCE)
    async with sessions.begin() as session:
        await session.execute(
            update(LoginFlowRecord).values(
                created_at=func.clock_timestamp() - timedelta(minutes=10),
                expires_at=func.clock_timestamp() - timedelta(minutes=5),
            )
        )
    with pytest.raises(GoogleRejectedError):
        await CompleteGoogleLogin(uow, provider, vault())(
            state=state_from(started.redirect_url), browser=started.browser, code=GoogleCode("code")
        )
    assert provider.calls == 0


async def test_deleted_subject_cannot_recreate_or_reactivate_account(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlLoginUnitOfWork(sessions)
    provider = GoogleProviderDouble()
    begin = BeginGoogleLogin(uow, provider, vault())
    complete = CompleteGoogleLogin(uow, provider, vault())
    started = await begin(return_to="/", source_digest=SOURCE)
    original = await complete(
        state=state_from(started.redirect_url), browser=started.browser, code=GoogleCode("code")
    )
    reader = ReadIdentity(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher())
    account_id = (await reader(original.credential)).session.account_id
    async with sessions.begin() as session:
        await session.execute(
            update(AccountRecord)
            .where(AccountRecord.id == account_id)
            .values(deleted_at=func.clock_timestamp())
        )
    with pytest.raises(UnauthenticatedError):
        await reader(original.credential)
    new_flow = await begin(return_to="/", source_digest=SOURCE)
    with pytest.raises(AccountUnavailableError):
        await complete(
            state=state_from(new_flow.redirect_url),
            browser=new_flow.browser,
            code=GoogleCode("code"),
        )
    async with sessions() as session:
        assert (await session.scalars(select(func.count()).select_from(AccountRecord))).one() == 1
        assert (await session.scalars(select(func.count()).select_from(SessionRecord))).one() == 1
        retained = (await session.scalars(select(ExternalIdentityRecord))).one()
        assert retained.subject == provider.subject


async def test_banned_subject_can_authenticate_only_in_restricted_state(
    identity_engine: AsyncEngine,
) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlLoginUnitOfWork(sessions)
    provider = GoogleProviderDouble()
    begin = BeginGoogleLogin(uow, provider, vault())
    complete = CompleteGoogleLogin(uow, provider, vault())
    started = await begin(return_to="/", source_digest=SOURCE)
    original = await complete(
        state=state_from(started.redirect_url), browser=started.browser, code=GoogleCode("code")
    )
    async with sessions.begin() as session:
        await session.execute(update(AccountRecord).values(banned_at=func.clock_timestamp()))
    reader = ReadIdentity(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher())
    assert (await reader(original.credential)).banned
    again = await begin(return_to="/", source_digest=SOURCE)
    returned = await complete(
        state=state_from(again.redirect_url), browser=again.browser, code=GoogleCode("code")
    )
    assert (await reader(returned.credential)).banned


async def test_concurrent_account_switches_do_not_deadlock(identity_engine: AsyncEngine) -> None:
    sessions = async_sessionmaker(identity_engine, expire_on_commit=False)
    uow = SqlLoginUnitOfWork(sessions)
    credentials = []
    for subject in ("first", "second"):
        provider = GoogleProviderDouble(subject)
        started = await BeginGoogleLogin(uow, provider, vault())(
            return_to="/", source_digest=SOURCE
        )
        credentials.append(
            (
                await CompleteGoogleLogin(uow, provider, vault())(
                    state=state_from(started.redirect_url),
                    browser=started.browser,
                    code=GoogleCode("code"),
                )
            ).credential
        )

    async def switch(subject: str, previous: SessionCredential) -> None:
        provider = GoogleProviderDouble(subject)
        started = await BeginGoogleLogin(uow, provider, vault())(
            return_to="/", source_digest=SOURCE
        )
        await CompleteGoogleLogin(uow, provider, vault())(
            state=state_from(started.redirect_url),
            browser=started.browser,
            code=GoogleCode("code"),
            previous=previous,
        )

    await asyncio.wait_for(
        asyncio.gather(switch("second", credentials[0]), switch("first", credentials[1])),
        timeout=10,
    )
    reader = ReadIdentity(SqlIdentityUnitOfWork(sessions), Sha256SessionHasher())
    for credential in credentials:
        with pytest.raises(UnauthenticatedError):
            await reader(credential)
