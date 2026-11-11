import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from aiobotocore.session import AioSession
from pydantic import SecretStr

from studymate import bootstrap
from studymate.config import MediaConfiguration
from studymate.domain.media import MediaObjectKind, MediaObjectRef


async def test_media_composition_uses_explicit_credentials_and_warms_files_offloop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = bootstrap._prepare_media_session
    main_thread = threading.get_ident()
    warmed: list[bool] = []

    def prepare() -> AioSession:
        assert threading.get_ident() != main_thread
        warmed.append(True)
        return original()

    monkeypatch.setattr(bootstrap, "_prepare_media_session", prepare)
    monkeypatch.setenv("AWS_PROFILE", "synthetic-profile-that-must-not-be-read")
    configuration = MediaConfiguration(
        endpoint_origin="https://storage.example.test",
        bucket="synthetic-bucket",
        region="us-east-1",
        access_key_id=SecretStr("synthetic-identifier"),
        secret_access_key=SecretStr(uuid4().hex),
    )
    async with bootstrap._open_media_storage(configuration) as storage:
        access = await storage.upload_access(
            MediaObjectRef(uuid4(), MediaObjectKind.UPLOAD),
            "image/png",
            datetime.now(UTC) + timedelta(seconds=60),
        )
        assert access.url == "https://storage.example.test/synthetic-bucket"
        assert "synthetic-identifier" not in repr(access)
    assert warmed == [True]
