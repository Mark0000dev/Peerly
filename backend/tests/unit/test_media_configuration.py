import pytest
from pydantic import SecretStr, ValidationError

from studymate.config import MediaConfiguration


def configuration() -> MediaConfiguration:
    return MediaConfiguration(
        endpoint_origin="https://storage.example.test",
        bucket="synthetic-bucket",
        region="us-east-1",
        access_key_id=SecretStr("synthetic-identifier"),
        secret_access_key=SecretStr("synthetic-signing-material"),
    )


@pytest.mark.parametrize(
    "origin",
    [
        "http://storage.example.test",
        "https://storage.example.test/path",
        "https://user:private@storage.example.test",
        "https://storage.example.test?private=value",
        "https://storage.example.test#private",
        "https://storage.example.test:0",
        "https://storage.example.test:broken",
        "https://storage.example.test private",
    ],
)
def test_storage_requires_trusted_explicit_origin(origin: str) -> None:
    values = configuration().model_dump()
    values["endpoint_origin"] = origin
    with pytest.raises(ValidationError):
        MediaConfiguration.model_validate(values)


@pytest.mark.parametrize("field", ["access_key_id", "secret_access_key"])
def test_storage_never_falls_back_to_host_authentication(field: str) -> None:
    values = configuration().model_dump()
    values[field] = SecretStr("")
    with pytest.raises(ValidationError, match="Explicit S3 credentials"):
        MediaConfiguration.model_validate(values)


@pytest.mark.parametrize("bucket", ["bad..bucket", "127.0.0.1", "Has-Uppercase", "a", "bad/bucket"])
def test_storage_bucket_rejects_invalid_addressing(bucket: str) -> None:
    values = configuration().model_dump()
    values["bucket"] = bucket
    with pytest.raises(ValidationError):
        MediaConfiguration.model_validate(values)


def test_storage_secrets_are_hidden_and_no_endpoint_is_invented() -> None:
    config = configuration()
    assert "synthetic-identifier" not in repr(config)
    assert "synthetic-signing-material" not in repr(config)
    with pytest.raises(ValidationError):
        MediaConfiguration.model_validate({})
