import re

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from studymate.config import ObservabilityConfiguration
from studymate.infrastructure.student_notifications.providers import ProviderKeyMaterial


class StudentNotificationWorkerSettings(BaseSettings):
    """Dedicated worker credentials, never inferred from a browser or optional preference."""

    model_config = SettingsConfigDict(
        env_prefix="STUDENT_NOTIFICATIONS_",
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )
    database_url: SecretStr

    @field_validator("database_url")
    @classmethod
    def require_asyncpg(cls, value: SecretStr) -> SecretStr:
        if make_url(value.get_secret_value()).drivername != "postgresql+asyncpg":
            raise ValueError("Student notification worker requires PostgreSQL asyncpg")
        return value


class StudentNotificationProviderSettings(BaseSettings):
    """Explicit optional provider configuration, shared by API and delivery worker."""

    model_config = SettingsConfigDict(
        env_prefix="STUDENT_NOTIFICATIONS_",
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        env_ignore_empty=True,
    )
    web_pem: SecretStr | None = None
    contact: SecretStr | None = None
    web_hosts: tuple[str, ...] = ()
    apns_pem: SecretStr | None = None
    apns_key_id: str | None = None
    apns_team: str | None = None
    apns_topic: str | None = None
    apns_sandbox: bool = False
    fcm_pem: SecretStr | None = None
    fcm_email: SecretStr | None = None
    fcm_project: str | None = None

    def key_material(self) -> ProviderKeyMaterial:
        return ProviderKeyMaterial(
            web_pem=None if self.web_pem is None else self.web_pem.get_secret_value().encode(),
            contact=None if self.contact is None else self.contact.get_secret_value(),
            web_hosts=self.web_hosts,
            apns_pem=None if self.apns_pem is None else self.apns_pem.get_secret_value().encode(),
            apns_key_id=self.apns_key_id,
            apns_team=self.apns_team,
            apns_topic=self.apns_topic,
            apns_sandbox=self.apns_sandbox,
            fcm_pem=None if self.fcm_pem is None else self.fcm_pem.get_secret_value().encode(),
            fcm_email=None if self.fcm_email is None else self.fcm_email.get_secret_value(),
            fcm_project=self.fcm_project,
        )


class StudentNotificationDeliverySettings(
    StudentNotificationWorkerSettings, StudentNotificationProviderSettings
):
    model_config = SettingsConfigDict(
        env_prefix="STUDENT_NOTIFICATIONS_",
        env_nested_delimiter="__",
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        env_ignore_empty=True,
    )
    observability: ObservabilityConfiguration | None = None
    envelope_key: SecretStr

    @field_validator("envelope_key")
    @classmethod
    def require_envelope(cls, value: SecretStr) -> SecretStr:
        if re.fullmatch(r"[0-9a-fA-F]{64}", value.get_secret_value()) is None:
            raise ValueError("Student delivery envelope key must be32byte hexadecimal")
        return value
