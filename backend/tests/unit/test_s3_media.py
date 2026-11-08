import asyncio
import base64
import json
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from aiobotocore.config import AioConfig
from aiobotocore.session import get_session
from aiobotocore.stub import AioStubber
from types_aiobotocore_s3.client import S3Client

from studymate.application.media.processing import MAX_SOURCE_BYTES, ImageFailure, InvalidImageError
from studymate.application.media.storage import (
    MediaObjectMissingError,
    MediaStorageUnavailableError,
    MediaUploadAccessExpiredError,
)
from studymate.domain.media import MediaObjectKind, MediaObjectRef
from studymate.infrastructure.media.s3 import S3MediaStorage, object_key

SIGNING_MATERIAL = uuid4().hex


@pytest.fixture
async def s3_client() -> AsyncIterator[S3Client]:
    session = get_session()
    session.set_config_variable("config_file", "/dev/null")
    session.set_config_variable("credentials_file", "/dev/null")
    async with session.create_client(
        "s3",
        region_name="us-east-1",
        endpoint_url="https://storage.example.test",
        aws_access_key_id="synthetic-key",
        aws_secret_access_key=SIGNING_MATERIAL,
        config=AioConfig(
            signature_version="s3v4",
            connect_timeout=1,
            read_timeout=1,
            retries={"max_attempts": 0},
            s3={"addressing_style": "path"},
        ),
    ) as client:
        yield client


def upload() -> MediaObjectRef:
    return MediaObjectRef(uuid4(), MediaObjectKind.UPLOAD)


async def test_presigned_form_is_bounded_purpose_specific_and_hidden_in_repr(
    s3_client: S3Client,
) -> None:
    storage = S3MediaStorage(s3_client, "synthetic-bucket")
    reference = upload()
    access = await storage.upload_access(
        reference, "image/png", datetime.now(UTC) + timedelta(seconds=60)
    )
    assert access.url == "https://storage.example.test/synthetic-bucket"
    fields = dict(access.fields)
    assert fields["key"] == object_key(reference)
    assert fields["Content-Type"] == "image/png"
    policy = json.loads(base64.b64decode(fields["policy"]))
    assert ["content-length-range", 1, MAX_SOURCE_BYTES] in policy["conditions"]
    assert {"key": object_key(reference)} in policy["conditions"]
    assert {"Content-Type": "image/png"} in policy["conditions"]
    assert "policy" in fields
    assert "x-amz-signature" in fields
    assert "synthetic-key" not in repr(access)
    assert "policy" not in repr(access)
    assert SIGNING_MATERIAL not in repr(storage)


@pytest.mark.parametrize("code", ["NoSuchKey", "AccessDenied"])
async def test_s3_provider_errors_do_not_expose_private_details(
    s3_client: S3Client, code: str
) -> None:
    reference = upload()
    storage = S3MediaStorage(s3_client, "synthetic-bucket")
    with AioStubber(s3_client) as stub:
        stub.add_client_error(
            "get_object",
            service_error_code=code,
            service_message="private provider text",
            expected_params={
                "Bucket": storage.bucket,
                "Key": object_key(reference),
                "Range": f"bytes=0-{MAX_SOURCE_BYTES}",
            },
        )
        expected = MediaObjectMissingError if code == "NoSuchKey" else MediaStorageUnavailableError
        with pytest.raises(expected) as failed:
            await storage.read(reference)
        assert "private" not in str(failed.value)
        stub.assert_no_pending_responses()


async def test_retention_is_conditional_and_cleanup_cannot_delete_retained_business_data(
    s3_client: S3Client,
) -> None:
    reference = MediaObjectRef(uuid4(), MediaObjectKind.ORIGINAL, uuid4())
    storage = S3MediaStorage(s3_client, "synthetic-bucket")
    with AioStubber(s3_client) as stub:
        stub.add_response(
            "put_object",
            {},
            expected_params={
                "Bucket": storage.bucket,
                "Key": object_key(reference),
                "Body": b"private original",
                "ContentType": "image/png",
                "IfNoneMatch": "*",
            },
        )
        await storage.retain(reference, b"private original", "image/png")
        stub.assert_no_pending_responses()
    with pytest.raises(ValueError, match="cannot be cleaned"):
        await storage.remove_transport(reference)
    with pytest.raises(ValueError, match="Retention"):
        await storage.retain(upload(), b"private original", "image/png")
    with pytest.raises(ValueError, match="Upload access"):
        await storage.upload_access(
            reference, "image/png", datetime.now(UTC) + timedelta(seconds=60)
        )


async def test_transport_delete_and_storage_failure_mapping(s3_client: S3Client) -> None:
    reference = upload()
    storage = S3MediaStorage(s3_client, "synthetic-bucket")
    with AioStubber(s3_client) as stub:
        stub.add_response(
            "delete_object",
            {},
            expected_params={"Bucket": storage.bucket, "Key": object_key(reference)},
        )
        await storage.remove_transport(reference)
        stub.add_client_error("delete_object", service_error_code="AccessDenied")
        with pytest.raises(MediaStorageUnavailableError):
            await storage.remove_transport(reference)
        stub.add_client_error("put_object", service_error_code="AccessDenied")
        with pytest.raises(MediaStorageUnavailableError):
            await storage.retain(
                MediaObjectRef(reference.upload_id, MediaObjectKind.DISPLAY, uuid4()),
                b"photo",
                "image/jpeg",
            )
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("too_large", [False, True])
async def test_real_async_s3_response_is_bounded_and_connection_closed(too_large: bool) -> None:
    received = asyncio.Event()
    body = b"private image bytes" * 8000 if not too_large else b"oversized"
    requests: list[bytes] = []

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            requests.append(await reader.readuntil(b"\r\n\r\n"))
            size = MAX_SOURCE_BYTES + 1 if too_large else len(body)
            writer.write(
                f"HTTP/1.1 200 OK\r\nContent-Length: {size}\r\nConnection: close\r\n\r\n".encode()
                + body[:10]
            )
            await writer.drain()
            if not too_large:
                await asyncio.sleep(0.01)
                writer.write(body[10:])
                await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            received.set()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    try:
        address: object = server.sockets[0].getsockname()
        assert isinstance(address, tuple)
        port = address[1]
        assert isinstance(port, int)
        session = get_session()
        session.set_config_variable("config_file", "/dev/null")
        session.set_config_variable("credentials_file", "/dev/null")
        async with session.create_client(
            "s3",
            region_name="us-east-1",
            endpoint_url=f"http://127.0.0.1:{port}",
            aws_access_key_id="synthetic-key",
            aws_secret_access_key=SIGNING_MATERIAL,
            config=AioConfig(connect_timeout=1, read_timeout=1, retries={"max_attempts": 0}),
        ) as client:
            storage = S3MediaStorage(client, "synthetic-bucket")
            if too_large:
                with pytest.raises(InvalidImageError) as failed:
                    await storage.read(upload())
                assert failed.value.reason == ImageFailure.TOO_LARGE
            else:
                assert await storage.read(upload()) == body
        await asyncio.wait_for(received.wait(), timeout=2)
        assert len(requests) == 1
        assert f"Range: bytes=0-{MAX_SOURCE_BYTES}".encode() in requests[0]
    finally:
        server.close()
        await server.wait_closed()


def test_media_references_never_accept_arbitrary_storage_paths() -> None:
    reference = upload()
    with pytest.raises(ValueError, match="attempt identity"):
        replace(reference, kind=MediaObjectKind.DISPLAY)
    with pytest.raises(ValueError, match="attempt identity"):
        replace(reference, attempt_id=uuid4())
    retained = MediaObjectRef(reference.upload_id, MediaObjectKind.DISPLAY, uuid4())
    assert object_key(retained).endswith("/photo.jpg")
    assert object_key(retained).startswith("retained/")


@pytest.mark.parametrize("same_bytes", [True, False])
async def test_retention_retry_never_overwrites_different_attempt_bytes(
    s3_client: S3Client, monkeypatch: pytest.MonkeyPatch, same_bytes: bool
) -> None:
    reference = MediaObjectRef(uuid4(), MediaObjectKind.ORIGINAL, uuid4())
    storage = S3MediaStorage(s3_client, "synthetic-bucket")

    async def read(_self: S3MediaStorage, requested: MediaObjectRef) -> bytes:
        assert requested == reference
        return b"original" if same_bytes else b"different"

    monkeypatch.setattr(S3MediaStorage, "read", read)
    with AioStubber(s3_client) as stub:
        stub.add_client_error(
            "put_object", service_error_code="PreconditionFailed", http_status_code=412
        )
        if same_bytes:
            await storage.retain(reference, b"original", "image/png")
        else:
            with pytest.raises(MediaStorageUnavailableError):
                await storage.retain(reference, b"original", "image/png")
        stub.assert_no_pending_responses()


async def test_expired_upload_access_never_extends_original_deadline(s3_client: S3Client) -> None:
    storage = S3MediaStorage(s3_client, "synthetic-bucket")
    with pytest.raises(MediaUploadAccessExpiredError):
        await storage.upload_access(upload(), "image/png", datetime.now(UTC) - timedelta(seconds=1))
