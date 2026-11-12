"""Loopback-only FastAPI/PostgreSQL fixture. No external provider calls or secrets."""

import asyncio
import os
import shutil
import signal
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlencode
from uuid import UUID, uuid4

import uvicorn
from alembic import command
from alembic.config import Config
from chats_fixture import seed_chats, send_incoming_chat
from composer_fixture import seed_composer
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi import FastAPI, HTTPException, Request, Response
from media_fixture import ControlledMedia
from operator_fixture import (
    OPERATOR_NAMESPACES,
    operator_audit_summary,
    seed_operator,
    set_operator_grant,
)
from people_fixture import (
    CHAT_SUBJECTS,
    COMPOSER_SUBJECTS,
    DISCOVERY_SUBJECTS,
    seed_discovery,
    seed_people,
)
from pydantic import SecretStr
from requests_fixture import seed_requests
from sqlalchemy import func, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema
from starlette.middleware.cors import CORSMiddleware
from study_fixture import STUDY_NAMESPACES, seed_study, study_state

import studymate.bootstrap as composition
import studymate.presentation.request_correlation as correlation
from studymate.application.changes.publication import PublishChanges
from studymate.application.chat_images.worker import ProcessNextChatImage
from studymate.application.identity.email_delivery import (
    DeliverVerificationEmail,
    VerificationEmail,
)
from studymate.application.identity.google import (
    GoogleAuthorization,
    GoogleCode,
    GoogleUnavailableError,
)
from studymate.application.identity.sessions import SessionCredential
from studymate.application.media.worker import ProcessNextPhoto
from studymate.config import AuthenticationConfiguration, MediaConfiguration, Settings
from studymate.domain.membership import GOOGLE_ISSUER, GoogleIdentity
from studymate.infrastructure.ai.models import AiIntentRecord, AiJobRecord
from studymate.infrastructure.changes.publication import SqlChangePublicationUnitOfWork
from studymate.infrastructure.chat_images.worker import SqlChatImageWorkerUnitOfWork
from studymate.infrastructure.media.images import BoundedImageProcessor
from studymate.infrastructure.persistence.catalogue_models import (
    SubjectAliasRecord,
    SubjectRecord,
)
from studymate.infrastructure.persistence.email_delivery import SqlEmailWorkerUnitOfWork
from studymate.infrastructure.persistence.identity_models import (
    AccountRecord,
    ExternalIdentityRecord,
    SessionRecord,
)
from studymate.infrastructure.persistence.photo_worker import SqlPhotoWorkerUnitOfWork
from studymate.infrastructure.persistence.registration_models import (
    PolicyDocumentRecord,
)
from studymate.infrastructure.security.email_vault import AeadEmailVault
from studymate.presentation.browser import SESSION_COOKIE

# Explicit disposable fixture settings, not developer environment or production data.
DATABASE = "postgresql+asyncpg://studymate:studymate@127.0.0.1:5433/studymate_test"
AI_POOL_SIZE = 2
AI_POOL_TIMEOUT = 0.25
ACCOUNT = UUID("00000000-0000-0000-0000-000000000001")


class ControlledGoogle:
    """Test provider boundary only; all state/cookie/session use cases remain real."""

    async def authorization_url(self, authorization: GoogleAuthorization) -> str:
        return "https://provider.invalid/authorize?" + urlencode({"state": authorization.state})

    async def exchange(
        self, code: GoogleCode, authorization: GoogleAuthorization
    ) -> GoogleIdentity:
        if not authorization.nonce or not authorization.verifier:
            raise RuntimeError("Missing real authorization material")
        if code.value == "fixture-unavailable":
            raise GoogleUnavailableError
        return GoogleIdentity(GOOGLE_ISSUER, "frontend-fixture-" + code.value)


class CapturedEmail:
    """Controlled delivery boundary; no SMTP or external email."""

    def __init__(self) -> None:
        self.messages: dict[str, tuple[UUID, str]] = {}

    async def send(self, message: VerificationEmail, delivery_id: UUID) -> None:
        self.messages[message.email.value] = (delivery_id, message.code.value)


def write_tls(directory: Path) -> None:
    # Ephemeral loopback TLS allows genuine Secure __Host cookies in every browser.
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    (directory / "cert.pem").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path = directory / "key.pem"
    key_path.touch(mode=0o600, exist_ok=True)
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


async def seed_base(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:

        def migrate(sync_connection: Connection) -> None:
            configuration = Config("alembic.ini")
            configuration.attributes["connection"] = sync_connection
            command.upgrade(configuration, "head")

        await connection.run_sync(migrate)
    async with async_sessionmaker(engine)() as session, session.begin():
        now = await session.scalar(select(func.clock_timestamp()))
        if not isinstance(now, datetime):
            raise TypeError("Fixture requires the database wall clock")
        session.add(AccountRecord(id=ACCOUNT, created_at=now, banned_at=None, deleted_at=None))
        await session.flush()
        for marker in ("a", "b", "c"):
            session.add(
                SessionRecord(
                    id=uuid4(),
                    account_id=ACCOUNT,
                    secret_digest=sha256((marker * 43).encode()).digest(),
                    issued_at=now,
                    expires_at=now + timedelta(hours=1),
                    revoked_at=None,
                )
            )
        subjects = (("Calculus", "Calc 1"), ("SQL", "Databases"))
        for index, (name, _alias) in enumerate(subjects, start=30):
            session.add(
                SubjectRecord(
                    id=UUID(int=index),
                    name=name,
                    normalized_name=name.lower(),
                    created_at=now,
                    archived_at=None,
                )
            )
        await session.flush()
        for index, (_name, alias) in enumerate(subjects, start=30):
            session.add(
                SubjectAliasRecord(
                    subject_id=UUID(int=index),
                    slot=0,
                    name=alias,
                    normalized_alias=alias.lower(),
                )
            )
        for index, (kind, title) in enumerate(
            (("terms", "Terms of Use"), ("privacy", "Privacy Policy")), start=10
        ):
            session.add(
                PolicyDocumentRecord(
                    id=UUID(int=index),
                    kind=kind,
                    version="fixture-v1",
                    title=title,
                    content="Published " + kind + " fixture from PostgreSQL.",
                    published_at=datetime(2020, 1, 1, tzinfo=UTC),
                )
            )


def create_fixture_app(
    engine: AsyncEngine, ai_engine: AsyncEngine, change_engine: AsyncEngine
) -> FastAPI:
    # Fixed diagnostic UUID in this isolated process keeps screenshots deterministic;
    # production correlation generation/uniqueness is covered by backend tests.
    correlation.uuid4 = lambda: UUID("00000000-0000-0000-0000-000000000099")
    original_provider = composition.GoogleOidcProvider
    composition.GoogleOidcProvider = lambda *_args, **_kwargs: ControlledGoogle()
    original_factory = composition.create_async_engine
    original_change_factory = composition.create_change_read_engine

    # Change reads have the same limits as AI but must never share its pool.
    # Construct through the real named factory before intercepting core/AI.
    def fixture_change_engine(
        database_url: str, *, server_settings: Mapping[str, str] | None = None
    ) -> AsyncEngine:
        if database_url != DATABASE or server_settings is not None:
            raise ValueError("Unexpected change-read factory configuration")
        return change_engine

    # Keep the actual independent core/admission pools in the same disposable schema.
    # Fail closed if bootstrap changes the tested pool topology; never share AI/core capacity.
    def fixture_engine(
        _url: str,
        *,
        pool_pre_ping: bool,
        connect_args: dict[str, object],
        pool_size: int | None = None,
        max_overflow: int | None = None,
        pool_timeout: float | None = None,
    ) -> AsyncEngine:
        if not pool_pre_ping:
            raise ValueError("Fixture expects production pool health checks")
        if (
            pool_size is None
            and max_overflow is None
            and pool_timeout is None
            and connect_args == {"timeout": 5, "server_settings": {"lock_timeout": "1000"}}
        ):
            return engine
        if (
            pool_size == AI_POOL_SIZE
            and max_overflow == 0
            and pool_timeout == AI_POOL_TIMEOUT
            and connect_args == {"timeout": 2, "server_settings": {"lock_timeout": "1000"}}
        ):
            return ai_engine
        raise ValueError("Unexpected application pool topology")

    composition.create_async_engine = fixture_engine
    composition.create_change_read_engine = fixture_change_engine
    try:
        app = composition.create_app(
            Settings(
                _env_file=None,
                observability=None,
                media=MediaConfiguration(
                    endpoint_origin="https://storage.invalid",
                    bucket="frontend-fixture",
                    region="local",
                    access_key_id=SecretStr("synthetic-fixture"),
                    secret_access_key=SecretStr("synthetic-fixture"),
                ),
                database_url=SecretStr(DATABASE),
                authentication=AuthenticationConfiguration(
                    client_id="synthetic-frontend-client",
                    client_secret=SecretStr("synthetic"),
                    public_origin=os.environ["STUDYMATE_TEST_PUBLIC_ORIGIN"],
                    envelope_key=SecretStr("01" * 32),
                    browser_signing_key=SecretStr("02" * 32),
                    code_key=SecretStr("03" * 32),
                ),
            )
        )
    finally:
        composition.create_async_engine = original_factory
        composition.create_change_read_engine = original_change_factory
        composition.GoogleOidcProvider = original_provider
    return app


def install_email_routes(app: FastAPI, engine: AsyncEngine) -> None:
    captured = CapturedEmail()
    deliver = DeliverVerificationEmail(
        SqlEmailWorkerUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        captured,
        AeadEmailVault(bytes.fromhex("03" * 32), bytes.fromhex("01" * 32)),
    )

    @app.post("/__fixture/deliver/{email}", include_in_schema=False)
    async def deliver_fixture(email: str) -> dict[str, str]:
        # Driver-only loopback control, not a production API or UI consumer.
        for _ in range(10):
            await deliver()
            if email in captured.messages:
                return {"code": captured.messages[email][1]}
        raise HTTPException(status_code=404, detail="No fixture message")

    @app.get("/__fixture/goal-ai/state/{project}", include_in_schema=False)
    async def goal_ai_fixture_state(project: str) -> dict[str, int]:
        if project not in {"chromium-mobile", "webkit-mobile", "chromium-desktop"}:
            raise HTTPException(status_code=400, detail="Unknown fixture project")
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            actor_id = await session.scalar(
                select(ExternalIdentityRecord.account_id).where(
                    ExternalIdentityRecord.issuer == GOOGLE_ISSUER,
                    ExternalIdentityRecord.subject == "frontend-fixture-fixture-goal-ai-" + project,
                )
            )
            if actor_id is None:
                raise HTTPException(status_code=404, detail="No fixture actor")
            jobs = await session.scalar(
                select(func.count(AiJobRecord.id)).where(AiJobRecord.actor_id == actor_id)
            )
            intents = await session.scalar(
                select(func.count())
                .select_from(AiIntentRecord)
                .where(AiIntentRecord.actor_id == actor_id)
            )
            if jobs is None or intents is None:
                raise TypeError("Fixture requires actual admission counts")
            return {"jobs": jobs, "intents": intents}


def create_storage_app(media: ControlledMedia) -> FastAPI:
    storage_app = FastAPI()
    storage_app.add_middleware(
        CORSMiddleware,
        allow_origins=[os.environ["STUDYMATE_TEST_PUBLIC_ORIGIN"]],
        allow_methods=["POST"],
        allow_headers=["content-type"],
        allow_credentials=False,
    )

    @storage_app.post("/uploads/{upload_id}", include_in_schema=False)
    async def transfer_fixture(upload_id: UUID, request: Request) -> Response:
        # Actual browser multipart reaches controlled loopback TLS storage in every engine.
        if "cookie" in request.headers or "x-csrf-token" in request.headers:
            raise HTTPException(status_code=400, detail="Application credentials reached storage")
        try:
            media.accept(
                upload_id,
                request.headers.get("content-type", ""),
                await request.body(),
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid controlled transfer") from None
        return Response(status_code=204)

    return storage_app


def install_worker_routes(
    app: FastAPI, engine: AsyncEngine, media: ControlledMedia, processor: BoundedImageProcessor
) -> tuple[ProcessNextPhoto, asyncio.Lock]:
    process_photo = ProcessNextPhoto(
        SqlPhotoWorkerUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        media,
        processor,
    )
    process_chat_image = ProcessNextChatImage(
        SqlChatImageWorkerUnitOfWork(async_sessionmaker(engine, expire_on_commit=False)),
        media,
        processor,
    )
    photo_step_lock = asyncio.Lock()
    chat_image_step_lock = asyncio.Lock()

    @app.post("/__fixture/chat-images/process", include_in_schema=False)
    async def process_chat_image_fixture() -> dict[str, str]:
        # Driver-only: run the actual worker, never patch canonical READY state.
        async with chat_image_step_lock:
            return {"outcome": (await process_chat_image()).value}

    @app.post("/__fixture/photo/process", include_in_schema=False)
    async def process_fixture() -> dict[str, str]:
        async with photo_step_lock:
            return {"outcome": (await process_photo()).value}

    return process_photo, photo_step_lock


def install_operator_routes(app: FastAPI, engine: AsyncEngine) -> None:
    operator_actors: set[UUID] = set()
    operator_cohorts: set[str] = set()

    @app.post("/__fixture/operator", include_in_schema=False, status_code=201)
    async def operator_fixture(request: Request) -> dict[str, str]:
        payload: object = await request.json()
        if not isinstance(payload, dict) or len(payload) != 1:
            raise HTTPException(status_code=400, detail="Invalid operator fixture")
        namespace: object = payload.get("namespace")
        if not isinstance(namespace, str) or namespace not in OPERATOR_NAMESPACES:
            raise HTTPException(status_code=400, detail="Invalid operator fixture")
        if namespace in operator_cohorts:
            raise HTTPException(status_code=409, detail="Controlled cohort already exists")
        operator_cohorts.add(namespace)
        result = await seed_operator(engine, namespace)
        operator_actors.update((UUID(result["viewer_id"]), UUID(result["replacement_id"])))
        return {
            **result,
            "origin": os.environ["STUDYMATE_TEST_PUBLIC_ORIGIN"],
            "cookie_name": SESSION_COOKIE,
        }

    @app.post("/__fixture/operator/{owner}/grant/{active}", include_in_schema=False)
    async def operator_grant_fixture(owner: UUID, active: bool) -> Response:
        if owner not in operator_actors:
            raise HTTPException(status_code=404, detail="Unknown controlled operator")
        await set_operator_grant(engine, owner, active=active)
        return Response(status_code=204)

    @app.get("/__fixture/operator/{owner}/audit", include_in_schema=False)
    async def operator_audit_fixture(owner: UUID) -> dict[str, int]:
        if owner not in operator_actors:
            raise HTTPException(status_code=404, detail="Unknown controlled operator")
        return await operator_audit_summary(engine, owner)


def install_study_routes(app: FastAPI, engine: AsyncEngine, media: ControlledMedia) -> None:
    study_cohorts: set[str] = set()
    study_actors: dict[UUID, UUID] = {}

    @app.post("/__fixture/study", include_in_schema=False, status_code=201)
    async def study_fixture(request: Request) -> dict[str, str]:
        payload: object = await request.json()
        if not isinstance(payload, dict) or len(payload) != 1:
            raise HTTPException(status_code=400, detail="Invalid study fixture")
        namespace: object = payload.get("namespace")
        if not isinstance(namespace, str) or namespace not in STUDY_NAMESPACES:
            raise HTTPException(status_code=400, detail="Invalid controlled study namespace")
        if namespace in study_cohorts:
            raise HTTPException(status_code=409, detail="Controlled study cohort exists")
        study_cohorts.add(namespace)
        result = await seed_study(engine, media, namespace)
        study_actors[UUID(result["conversation_id"])] = UUID(result["viewer_id"])
        return {
            **result,
            "origin": os.environ["STUDYMATE_TEST_PUBLIC_ORIGIN"],
            "cookie_name": SESSION_COOKIE,
        }

    @app.get("/__fixture/study/{conversation_id}/state", include_in_schema=False)
    async def study_state_fixture(conversation_id: UUID) -> dict[str, int]:
        owner = study_actors.get(conversation_id)
        if owner is None:
            raise HTTPException(status_code=404, detail="Unknown controlled study cohort")
        return await study_state(engine, conversation_id, owner)


def install_chat_routes(
    app: FastAPI,
    engine: AsyncEngine,
    media: ControlledMedia,
    process_photo: ProcessNextPhoto,
    photo_step_lock: asyncio.Lock,
) -> None:
    chat_peers: dict[UUID, SessionCredential] = {}

    @app.post("/__fixture/chats", include_in_schema=False, status_code=201)
    async def chats_fixture(request: Request) -> dict[str, str]:
        payload: object = await request.json()
        if not isinstance(payload, dict) or len(payload) != 1:
            raise HTTPException(status_code=400, detail="Invalid chat fixture")
        namespace: object = payload.get("namespace")
        if not isinstance(namespace, str) or namespace not in CHAT_SUBJECTS:
            raise HTTPException(status_code=400, detail="Invalid chat fixture")
        result = await seed_chats(engine, media, process_photo, photo_step_lock, namespace)
        chat_peers[UUID(result["conversation_id"])] = SessionCredential(result["peer_session"])
        return {
            **result,
            "origin": os.environ["STUDYMATE_TEST_PUBLIC_ORIGIN"],
            "cookie_name": SESSION_COOKIE,
        }

    @app.post("/__fixture/chats/{conversation_id}/incoming", include_in_schema=False)
    async def incoming_chat_fixture(conversation_id: UUID) -> dict[str, str]:
        credential = chat_peers.get(conversation_id)
        if credential is None:
            raise HTTPException(status_code=404, detail="Unknown controlled chat cohort")
        return await send_incoming_chat(engine, credential, conversation_id)


def install_changes_route(app: FastAPI, engine: AsyncEngine) -> None:
    publish_changes = PublishChanges(
        SqlChangePublicationUnitOfWork(async_sessionmaker(engine, expire_on_commit=False))
    )

    @app.post("/__fixture/changes/publish", include_in_schema=False)
    async def publish_changes_fixture() -> dict[str, int]:
        return {"published": await publish_changes()}


def install_student_routes(
    app: FastAPI,
    engine: AsyncEngine,
    media: ControlledMedia,
    process_photo: ProcessNextPhoto,
    photo_step_lock: asyncio.Lock,
) -> None:
    @app.post("/__fixture/people", include_in_schema=False, status_code=201)
    async def people_fixture() -> dict[str, str]:
        # Driver-only synthetic actors; actual save/worker/registration paths
        # establish readiness.
        result = await seed_people(engine, media, process_photo, photo_step_lock)
        return {
            **result,
            "origin": os.environ["STUDYMATE_TEST_PUBLIC_ORIGIN"],
            "cookie_name": SESSION_COOKIE,
        }

    @app.post("/__fixture/discovery", include_in_schema=False, status_code=201)
    async def discovery_fixture(request: Request) -> dict[str, str]:
        payload: object = await request.json()
        if not isinstance(payload, dict) or len(payload) != 1:
            raise HTTPException(status_code=400, detail="Invalid fixture namespace")
        namespace: object = payload.get("namespace")
        if not isinstance(namespace, str) or namespace not in DISCOVERY_SUBJECTS:
            raise HTTPException(status_code=400, detail="Invalid fixture namespace")
        result = await seed_discovery(engine, media, process_photo, photo_step_lock, namespace)
        return {
            **result,
            "origin": os.environ["STUDYMATE_TEST_PUBLIC_ORIGIN"],
            "cookie_name": SESSION_COOKIE,
        }

    @app.post("/__fixture/composer", include_in_schema=False, status_code=201)
    async def composer_fixture(request: Request) -> dict[str, str]:
        payload: object = await request.json()
        if not isinstance(payload, dict) or len(payload) != 1:
            raise HTTPException(status_code=400, detail="Invalid composer fixture")
        namespace: object = payload.get("namespace")
        if not isinstance(namespace, str) or namespace not in COMPOSER_SUBJECTS:
            raise HTTPException(status_code=400, detail="Invalid composer fixture")
        result = await seed_composer(engine, media, process_photo, photo_step_lock, namespace)
        return {
            **result,
            "origin": os.environ["STUDYMATE_TEST_PUBLIC_ORIGIN"],
            "cookie_name": SESSION_COOKIE,
        }

    @app.post("/__fixture/requests", include_in_schema=False, status_code=201)
    async def requests_fixture(request: Request) -> dict[str, str]:
        payload: object = await request.json()
        if not isinstance(payload, dict) or len(payload) != 1:
            raise HTTPException(status_code=400, detail="Invalid request fixture")
        direction: object = payload.get("direction")
        if not isinstance(direction, str) or direction not in {"received", "sent"}:
            raise HTTPException(status_code=400, detail="Invalid request fixture")
        result = await seed_requests(engine, media, process_photo, photo_step_lock, direction)
        return {
            **result,
            "origin": os.environ["STUDYMATE_TEST_PUBLIC_ORIGIN"],
            "cookie_name": SESSION_COOKIE,
        }


async def serve_fixture(
    app: FastAPI,
    storage_app: FastAPI,
    media: ControlledMedia,
    processor: BoundedImageProcessor,
    tls_directory: Path,
) -> None:
    original_storage = composition._open_media_storage
    composition._open_media_storage = media.open
    storage_server = uvicorn.Server(
        uvicorn.Config(
            storage_app,
            host="127.0.0.1",
            port=8769,
            access_log=False,
            ssl_certfile=str(tls_directory / "cert.pem"),
            ssl_keyfile=str(tls_directory / "key.pem"),
        )
    )
    storage_task = asyncio.create_task(storage_server.serve())
    try:
        await uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=8768, access_log=False)
        ).serve()
    finally:
        composition._open_media_storage = original_storage
        storage_server.should_exit = True
        await storage_task
        await processor.close()


async def main() -> None:
    tls_directory = Path(os.environ["STUDYMATE_TEST_TLS_DIRECTORY"])
    await asyncio.to_thread(write_tls, tls_directory)
    schema = "frontend_" + uuid4().hex
    admin = create_async_engine(DATABASE)
    async with admin.begin() as connection:
        await connection.execute(CreateSchema(schema))
    engine = create_async_engine(
        DATABASE,
        pool_pre_ping=True,
        connect_args={
            "timeout": 5,
            "server_settings": {"lock_timeout": "1000", "search_path": schema},
        },
    )
    ai_engine = create_async_engine(
        DATABASE,
        pool_pre_ping=True,
        pool_size=AI_POOL_SIZE,
        max_overflow=0,
        pool_timeout=AI_POOL_TIMEOUT,
        connect_args={
            "timeout": 2,
            "server_settings": {"lock_timeout": "1000", "search_path": schema},
        },
    )
    change_engine = composition.create_change_read_engine(
        DATABASE, server_settings={"search_path": schema}
    )
    try:
        await seed_base(engine)
        app = create_fixture_app(engine, ai_engine, change_engine)
        install_email_routes(app, engine)
        media = ControlledMedia()
        processor = BoundedImageProcessor()
        process_photo, photo_step_lock = install_worker_routes(app, engine, media, processor)
        install_operator_routes(app, engine)
        install_study_routes(app, engine, media)
        install_chat_routes(app, engine, media, process_photo, photo_step_lock)
        install_student_routes(app, engine, media, process_photo, photo_step_lock)
        install_changes_route(app, engine)
        await serve_fixture(app, create_storage_app(media), media, processor, tls_directory)
    finally:
        await change_engine.dispose()
        await ai_engine.dispose()
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await admin.dispose()
        await asyncio.to_thread(shutil.rmtree, tls_directory)


if __name__ == "__main__":
    # Uvicorn re-emits SIGTERM after shutdown; let fixture finally clean its schema.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    asyncio.run(main())
