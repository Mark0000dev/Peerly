"""Explicit synthetic files through the real CLI and student API, never runtime defaults."""

import argparse
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from studymate.application.identity.sessions import SessionCredential
from studymate.bootstrap_data_cli import dispatch
from studymate.infrastructure.bootstrap_data import runtime
from studymate.infrastructure.operator.models import OperatorAccessRecord
from studymate.infrastructure.persistence.identity_models import AccountRecord
from studymate.infrastructure.persistence.registration_models import (
    RegistrationContextRecord,
    RegistrationReceiptRecord,
)
from studymate.presentation.bootstrap_data.inputs import BootstrapInput
from studymate.presentation.browser import SESSION_COOKIE
from studymate.presentation.identity import IdentityResponse
from studymate.presentation.registration_models import (
    RegistrationContextResponse,
    RegistrationReceiptResponse,
)
from tests.integration.http_identity import BrowserHarness, write_headers
from tests.integration.onboarding_fixture import ready_setup
from tests.integration.test_registration_http import verify_student
from tests.unit.bootstrap_data.data import SUBJECT_ID, batch, encoded

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class ExplicitBootstrapImport:
    engine: AsyncEngine
    database_url: str = field(repr=False)
    monkeypatch: pytest.MonkeyPatch = field(repr=False)
    tmp_path: Path
    capsys: pytest.CaptureFixture[str] = field(repr=False)

    async def apply(self, catalogue: bool) -> None:
        value = BootstrapInput.model_validate_json(encoded())
        if not catalogue:
            value = value.model_copy(update={"catalogue": None})
        path = self.tmp_path / "explicit-synthetic-bootstrap.json"
        path.write_text(value.model_dump_json(), encoding="utf-8")

        def isolated_engine(_url: object, **options: object) -> AsyncEngine:
            assert options["pool_size"] == 1
            return self.engine

        self.monkeypatch.setenv("DATABASE_URL", self.database_url)
        self.monkeypatch.setattr(runtime, "create_async_engine", isolated_engine)
        self.capsys.readouterr()
        assert await dispatch(argparse.Namespace(command="apply", file=str(path))) == 0
        output = self.capsys.readouterr()
        assert not output.err
        assert '"status": "applied"' in output.out
        assert "PRIVATE" not in output.out
        assert self.database_url not in output.out


@pytest.fixture
def bootstrap_importer(
    identity_engine: AsyncEngine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> ExplicitBootstrapImport:
    return ExplicitBootstrapImport(identity_engine, database_url, monkeypatch, tmp_path, capsys)


async def assert_no_implicit_student_completion(engine: AsyncEngine) -> None:
    async with async_sessionmaker(engine)() as session:
        assert await session.scalar(select(func.count()).select_from(AccountRecord)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(RegistrationContextRecord)) == 0
        )
        assert (
            await session.scalar(select(func.count()).select_from(RegistrationReceiptRecord)) == 0
        )
        assert await session.scalar(select(func.count()).select_from(OperatorAccessRecord)) == 0


async def helper_selection(browser: BrowserHarness, status: HTTPStatus) -> None:
    response = await browser.client.put(
        "/api/v1/me/help-subjects",
        json={"subjects": [{"subject_id": str(SUBJECT_ID)}], "expected_version": 0},
        headers=await write_headers(browser.client),
    )
    assert response.status_code == status, response.text
    if status == HTTPStatus.CONFLICT:
        assert response.json()["code"] == "subject_unavailable"


@pytest.mark.parametrize("catalogue", [False, True], ids=["custom-learner", "canonical-helper"])
async def test_actual_firstboot_files_and_notice_unlock_only_supported_student_paths(
    browser: BrowserHarness,
    identity_engine: AsyncEngine,
    bootstrap_importer: ExplicitBootstrapImport,
    catalogue: bool,
) -> None:
    assert (await browser.client.get("/api/v1/policies/terms")).status_code == HTTPStatus.NOT_FOUND
    await verify_student(browser, identity_engine)
    cookie = browser.client.cookies.get(SESSION_COOKIE)
    assert cookie is not None
    await ready_setup(identity_engine, SessionCredential(cookie))
    assert (await browser.client.get("/api/v1/subjects")).json()["items"] == []
    assert (await browser.client.get("/api/v1/me/goal")).json()["goal"]["subject"][
        "kind"
    ] == "custom"
    await helper_selection(browser, HTTPStatus.CONFLICT)
    missing = await browser.client.post(
        "/api/v1/me/registration-context", headers=await write_headers(browser.client)
    )
    assert missing.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert missing.json()["code"] == "registration_documents_unavailable"
    await bootstrap_importer.apply(catalogue)
    await assert_no_implicit_student_completion(identity_engine)
    legal = await browser.client.get("/api/v1/policies/terms")
    assert legal.status_code == HTTPStatus.OK
    assert legal.json()["content"] == batch().policies[0].content
    if catalogue:
        updated = await browser.client.put(
            "/api/v1/me/profile",
            json={"display_name": "Synthetic student", "task": "offer_help", "expected_version": 1},
            headers=await write_headers(browser.client),
        )
        assert updated.status_code == HTTPStatus.OK, updated.text
    context_response = await browser.client.post(
        "/api/v1/me/registration-context", headers=await write_headers(browser.client)
    )
    assert context_response.status_code == HTTPStatus.CREATED, context_response.text
    context = RegistrationContextResponse.model_validate(context_response.json())
    if catalogue:
        incomplete = await browser.client.post(
            "/api/v1/me/registration",
            json={"context_id": str(context.id)},
            headers=await write_headers(browser.client),
        )
        assert incomplete.status_code == HTTPStatus.CONFLICT
        assert incomplete.json()["code"] == "onboarding_incomplete"
        await helper_selection(browser, HTTPStatus.OK)
    else:
        await helper_selection(browser, HTTPStatus.CONFLICT)
    completed = await browser.client.post(
        "/api/v1/me/registration",
        json={"context_id": str(context.id)},
        headers=await write_headers(browser.client),
    )
    assert completed.status_code == HTTPStatus.OK, completed.text
    receipt = RegistrationReceiptResponse.model_validate(completed.json())
    assert receipt.context_id == context.id
    assert receipt.terms == context.terms
    assert receipt.privacy == context.privacy
    actual = IdentityResponse.model_validate((await browser.client.get("/api/v1/me")).json())
    assert actual.registration == receipt
    assert actual.capabilities.can_use_student_features
