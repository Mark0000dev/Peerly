"""Actual pinned SDK/TLS sockets, synthetic CA and bytes; no mocked client or provider."""

import ipaddress
import ssl
import threading
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from aiohttp import web
from botocore.exceptions import SSLError
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pydantic import SecretStr

from studymate import bootstrap
from studymate.application.media.storage import MediaStorageUnavailableError
from studymate.config import MediaConfiguration
from studymate.domain.media import MAX_PHOTO_BYTES, MediaObjectKind, MediaObjectRef

BODY = b"synthetic storage TLS fixture, not a user photo"


@dataclass(frozen=True, slots=True)
class TlsMaterial:
    context: ssl.SSLContext
    ca_file: Path


@pytest.fixture
def tls_material(tmp_path: Path) -> TlsMaterial:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Synthetic fixture CA")])
    now = datetime.now(UTC)
    ca = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    server_key = ec.generate_private_key(ec.SECP256R1())
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")]))
        .issuer_name(name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.DNSName("localhost")]
            ),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )
    ca_file, cert_file, key_file = (tmp_path / name for name in ("ca.pem", "server.pem", "key.pem"))
    ca_file.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    key_file.chmod(0o600)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    return TlsMaterial(context, ca_file)


@dataclass(frozen=True, slots=True)
class RequestProof:
    method: str
    range: str | None
    if_none_match: str | None
    signed: bool
    body: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class TlsEndpoint:
    origin: str
    requests: list[RequestProof]


@pytest.fixture
async def tls_s3(tls_material: TlsMaterial, unused_tcp_port: int) -> AsyncIterator[TlsEndpoint]:
    requests: list[RequestProof] = []

    async def handle(request: web.Request) -> web.Response:
        body = await request.read()
        requests.append(
            RequestProof(
                request.method,
                request.headers.get("Range"),
                request.headers.get("If-None-Match"),
                request.headers.get("Authorization", "").startswith("AWS4-HMAC-SHA256 "),
                body,
            )
        )
        if request.method == "GET":
            return web.Response(
                status=206,
                body=BODY,
                headers={"Content-Range": f"bytes 0-{len(BODY) - 1}/{len(BODY)}"},
            )
        return web.Response(status=200)

    app = web.Application(client_max_size=MAX_PHOTO_BYTES)
    app.router.add_route("*", "/{path:.*}", handle)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(
            runner, "127.0.0.1", unused_tcp_port, ssl_context=tls_material.context
        ).start()
        yield TlsEndpoint(f"https://127.0.0.1:{unused_tcp_port}", requests)
    finally:
        await runner.cleanup()


def configuration(endpoint: TlsEndpoint) -> MediaConfiguration:
    return MediaConfiguration(
        endpoint_origin=endpoint.origin,
        bucket="synthetic-bucket",
        region="us-east-1",
        access_key_id=SecretStr("synthetic-fixture-identifier"),
        secret_access_key=SecretStr(uuid4().hex),
    )


async def test_actual_sdk_verified_https_read_and_conditional_retain_ca_io_offloop(
    tls_s3: TlsEndpoint, tls_material: TlsMaterial, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AWS_CA_BUNDLE", str(tls_material.ca_file))
    original = ssl.SSLContext.load_verify_locations
    main_thread = threading.get_ident()
    loads: list[tuple[int, ssl.VerifyMode, bool]] = []

    def load(
        context: ssl.SSLContext,
        cafile: str | None = None,
        capath: str | None = None,
        cadata: str | bytes | None = None,
    ) -> None:
        loads.append((threading.get_ident(), context.verify_mode, context.check_hostname))
        original(context, cafile, capath, cadata)

    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", load)
    upload_id = uuid4()
    async with bootstrap._open_media_storage(configuration(tls_s3)) as storage:
        assert await storage.read(MediaObjectRef(upload_id, MediaObjectKind.UPLOAD)) == BODY
        await storage.retain(
            MediaObjectRef(upload_id, MediaObjectKind.ORIGINAL, uuid4()), BODY, "image/jpeg"
        )
    assert [item.method for item in tls_s3.requests] == ["GET", "PUT"]
    assert tls_s3.requests[0].range == f"bytes=0-{MAX_PHOTO_BYTES}"
    assert tls_s3.requests[1].if_none_match == "*"
    assert tls_s3.requests[1].body == BODY
    assert all(item.signed for item in tls_s3.requests)
    assert loads
    assert all(thread != main_thread for thread, _, _ in loads)
    assert all(mode == ssl.CERT_REQUIRED for _, mode, _ in loads)
    assert all(hostname for _, _, hostname in loads)


async def test_actual_sdk_rejects_untrusted_https_certificate(
    tls_s3: TlsEndpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AWS_CA_BUNDLE", raising=False)
    async with bootstrap._open_media_storage(configuration(tls_s3)) as storage:
        with pytest.raises(MediaStorageUnavailableError) as failed:
            await storage.read(MediaObjectRef(uuid4(), MediaObjectKind.UPLOAD))
    assert isinstance(failed.value.__cause__, SSLError)
    assert tls_s3.requests == []
