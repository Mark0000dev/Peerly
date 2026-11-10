import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from studymate.infrastructure.email.reply_to import require_reply_to

AUTHENTICATION_KEY_COUNT = 3
MAX_AI_ACCOUNT_BINDING_LENGTH = 255


class AuthenticationConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    client_id: str = Field(min_length=1, max_length=255)
    client_secret: SecretStr
    public_origin: str
    envelope_key: SecretStr
    browser_signing_key: SecretStr
    code_key: SecretStr
    callback_failures_per_hour: int = Field(default=30, ge=1, le=10000)
    google_starts_per_hour: int = Field(default=30, ge=1, le=10000)
    email_deliveries_per_account_hour: int = Field(default=5, ge=1, le=1000)
    email_deliveries_per_address_hour: int = Field(default=5, ge=1, le=1000)
    email_starts_per_source_hour: int = Field(default=30, ge=1, le=10000)

    @field_validator("envelope_key", "browser_signing_key", "code_key")
    @classmethod
    def require_key(cls, value: SecretStr) -> SecretStr:
        if not re.fullmatch(r"[0-9a-fA-F]{64}", value.get_secret_value()):
            raise ValueError("Authentication keys must be 32-byte hexadecimal secrets")
        return value

    @field_validator("public_origin")
    @classmethod
    def require_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
        ):
            raise ValueError("Public origin must be an HTTPS origin without a path")
        return value

    @model_validator(mode="after")
    def require_separate_keys(self) -> "AuthenticationConfiguration":
        keys = {
            key.get_secret_value().lower()
            for key in (
                self.envelope_key,
                self.browser_signing_key,
                self.code_key,
            )
        }
        if len(keys) != AUTHENTICATION_KEY_COUNT:
            raise ValueError("Envelope, code and browser signing keys must be distinct")
        if not self.client_secret.get_secret_value():
            raise ValueError("Google client secret is required")
        return self


class ObservabilityConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    collector_origin: str
    environment: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9-]+$")
    release: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    trace_queue_capacity: int = Field(default=512, ge=16, le=4096)

    @field_validator("collector_origin")
    @classmethod
    def require_collector_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        port = parsed.port
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or port == 0
            or any(character.isspace() for character in value)
        ):
            raise ValueError("Collector must be an HTTP(S) origin without credentials or a path")
        return value


class MediaConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    endpoint_origin: str
    bucket: str = Field(min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$")
    region: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    access_key_id: SecretStr
    secret_access_key: SecretStr

    @field_validator("endpoint_origin")
    @classmethod
    def require_storage_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        port = parsed.port
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or port == 0
            or any(character.isspace() for character in value)
        ):
            raise ValueError(
                "Storage endpoint must be an HTTPS origin without credentials or a path"
            )
        return value

    @model_validator(mode="after")
    def require_storage_credentials(self) -> "MediaConfiguration":
        if (
            not self.access_key_id.get_secret_value()
            or not self.secret_access_key.get_secret_value()
        ):
            raise ValueError("Explicit S3 credentials are required")
        if ".." in self.bucket or re.fullmatch(r"[0-9]+(\.[0-9]+){3}", self.bucket):
            raise ValueError("Storage bucket must be a DNS-compatible bucket name")
        return self


class AiHttpConfiguration(BaseModel):
    """Bounded HTTP reliability only; this cannot enable an executor."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    request_budget_seconds: float = Field(default=2, gt=0, le=2)
    retry_after_seconds: int = Field(default=1, ge=1, le=60)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="forbid",
        frozen=True,
        env_nested_delimiter="__",
        hide_input_in_errors=True,
    )

    database_url: SecretStr
    authentication: AuthenticationConfiguration | None = None
    media: MediaConfiguration | None = None
    observability: ObservabilityConfiguration | None = None
    ai: AiHttpConfiguration = Field(default_factory=AiHttpConfiguration)

    @field_validator("database_url")
    @classmethod
    def require_asyncpg(cls, value: SecretStr) -> SecretStr:
        url = make_url(value.get_secret_value())
        if url.drivername != "postgresql+asyncpg":
            msg = "DATABASE_URL must use postgresql+asyncpg"
            raise ValueError(msg)
        return value


class SmtpDeliveryConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    hostname: str = Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.-]+$")
    port: int = Field(ge=1, le=65535)
    username: SecretStr
    password: SecretStr
    sender: str = Field(
        min_length=3, max_length=254, pattern=r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+$"
    )
    mode: Literal["starttls", "tls"] = "starttls"
    reply_to: str | None = Field(default=None, repr=False)

    @field_validator("reply_to")
    @classmethod
    def require_reply_mailbox(cls, value: str | None) -> str | None:
        return require_reply_to(value) if value is not None else None

    @model_validator(mode="after")
    def require_credentials(self) -> "SmtpDeliveryConfiguration":
        if not self.username.get_secret_value() or not self.password.get_secret_value():
            raise ValueError("SMTP credentials are required")
        return self


class EmailWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.worker",
        extra="forbid",
        frozen=True,
        env_nested_delimiter="__",
        hide_input_in_errors=True,
    )
    database_url: SecretStr
    code_key: SecretStr
    envelope_key: SecretStr
    smtp: SmtpDeliveryConfiguration
    observability: ObservabilityConfiguration | None = None

    @field_validator("database_url")
    @classmethod
    def require_asyncpg(cls, value: SecretStr) -> SecretStr:
        return Settings.require_asyncpg(value)

    @field_validator("code_key", "envelope_key")
    @classmethod
    def require_key(cls, value: SecretStr) -> SecretStr:
        return AuthenticationConfiguration.require_key(value)

    @model_validator(mode="after")
    def require_distinct_keys(self) -> "EmailWorkerSettings":
        if self.code_key.get_secret_value().lower() == self.envelope_key.get_secret_value().lower():
            raise ValueError("Email code and envelope keys must be distinct")
        return self


class MediaWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.media-worker",
        extra="forbid",
        frozen=True,
        env_nested_delimiter="__",
        hide_input_in_errors=True,
    )
    database_url: SecretStr
    media: MediaConfiguration
    observability: ObservabilityConfiguration | None = None

    @field_validator("database_url")
    @classmethod
    def require_asyncpg(cls, value: SecretStr) -> SecretStr:
        return Settings.require_asyncpg(value)


class RequestsWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.requests-worker",
        extra="forbid",
        frozen=True,
        env_nested_delimiter="__",
        hide_input_in_errors=True,
    )
    database_url: SecretStr
    observability: ObservabilityConfiguration | None = None

    @field_validator("database_url")
    @classmethod
    def require_asyncpg(cls, value: SecretStr) -> SecretStr:
        return Settings.require_asyncpg(value)


class ChangesWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.changes-worker",
        extra="forbid",
        frozen=True,
        env_nested_delimiter="__",
        hide_input_in_errors=True,
    )
    database_url: SecretStr
    observability: ObservabilityConfiguration | None = None

    @field_validator("database_url")
    @classmethod
    def require_asyncpg(cls, value: SecretStr) -> SecretStr:
        return Settings.require_asyncpg(value)


class AiWorkerRuntimeConfiguration(BaseModel):
    """Explicit runtime inputs; configuration alone grants no provider readiness."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    executable: Path
    expected_version: str = Field(min_length=1, max_length=100)
    expected_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    model: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    credential_directory: Path
    expected_account: SecretStr
    expected_login_owner: SecretStr
    expected_oauth_issuer: str = Field(min_length=1, max_length=512)
    expected_oauth_client_id: str = Field(min_length=1, max_length=255)
    acceptance_artifact: Path
    workspaces_root: Path
    bubblewrap: Path = Path("/usr/bin/bwrap")
    prlimit: Path = Path("/usr/bin/prlimit")

    @field_validator("executable", "bubblewrap", "prlimit")
    @classmethod
    def require_runtime_binary(cls, value: Path) -> Path:
        if not value.is_absolute() or ".." in value.parts or not value.is_relative_to("/usr"):
            raise ValueError("Runtime binaries require explicit absolute paths under /usr")
        return value

    @field_validator("credential_directory", "workspaces_root")
    @classmethod
    def require_private_runtime_root(cls, value: Path) -> Path:
        if (
            not value.is_absolute()
            or value == Path("/")
            or ".." in value.parts
            or any(
                value.is_relative_to(root)
                for root in ("/home", "/root", "/usr", "/etc", "/proc", "/sys", "/dev")
            )
        ):
            raise ValueError("Dedicated non-home runtime directories are required")
        return value

    @field_validator("acceptance_artifact")
    @classmethod
    def require_explicit_acceptance_path(cls, value: Path) -> Path:
        if not value.is_absolute() or ".." in value.parts or value == Path("/"):
            raise ValueError("An explicit absolute runtime acceptance artifact is required")
        return value

    @field_validator("expected_account", "expected_login_owner")
    @classmethod
    def require_account_binding(cls, value: SecretStr) -> SecretStr:
        if (
            not value.get_secret_value().strip()
            or len(value.get_secret_value()) > MAX_AI_ACCOUNT_BINDING_LENGTH
        ):
            raise ValueError("An explicit bounded subscription account binding is required")
        return value

    @model_validator(mode="after")
    def require_disjoint_roots(self) -> "AiWorkerRuntimeConfiguration":
        if self.credential_directory.is_relative_to(
            self.workspaces_root
        ) or self.workspaces_root.is_relative_to(self.credential_directory):
            raise ValueError("Persistent credentials and disposable jobs require disjoint roots")
        return self


class AiWorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        extra="forbid",
        frozen=True,
        env_nested_delimiter="__",
        hide_input_in_errors=True,
    )

    database_url: SecretStr
    media: MediaConfiguration
    runtime: AiWorkerRuntimeConfiguration
    observability: ObservabilityConfiguration | None = None

    @field_validator("database_url")
    @classmethod
    def require_asyncpg(cls, value: SecretStr) -> SecretStr:
        return Settings.require_asyncpg(value)
