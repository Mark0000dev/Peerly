"""Strict credential-only subset of the pinned 0.167.0 AuthDotJson/TokenData.

Source: login/src/auth/storage.rs53 and login/src/token_data.rs11 at086ccc833.
Opaque token strings are NEVER decoded as identity/signature/expiry authority.
Owner-provisioned account/login/provenance metadata binds normal cache rotation.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator

from studymate.infrastructure.ai.credentials import MAX_CREDENTIAL_BYTES, CredentialDocument

MIN_OPAQUE_ASCII = 33
MAX_OPAQUE_ASCII = 126
MAX_BINDING_LENGTH = 512
MAX_REFRESH_TIMESTAMP = 64

Text = Annotated[StrictStr, Field(min_length=1, max_length=32768)]
Binding = Annotated[StrictStr, Field(min_length=1, max_length=512)]


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class _Authority(_Closed):
    issuer: Binding
    client_id: Binding


class _Tokens(_Closed):
    id_token: Text = Field(repr=False)
    access_token: Text = Field(repr=False)
    refresh_token: Text = Field(repr=False)
    account_id: Binding
    login_owner_id: Binding
    oauth_provenance: _Authority

    @field_validator("id_token", "access_token", "refresh_token", "account_id", "login_owner_id")
    @classmethod
    def bounded_opaque(cls, value: str) -> str:
        if value.strip() != value or any(
            ord(character) < MIN_OPAQUE_ASCII or ord(character) > MAX_OPAQUE_ASCII
            for character in value
        ):
            raise ValueError("credential_field")
        return value


class _Cache(_Closed):
    auth_mode: Literal["chatgpt"]
    OPENAI_API_KEY: None = None
    tokens: _Tokens = Field(repr=False)
    last_refresh: datetime | None = None
    agent_identity: None = None
    personal_access_token: None = None
    bedrock_api_key: None = None
    bedrock_access_keys: None = None

    @field_validator("last_refresh", mode="before")
    @classmethod
    def textual_refresh(cls, value: object) -> object:
        if value is not None and (not isinstance(value, str) or len(value) > MAX_REFRESH_TIMESTAMP):
            raise ValueError("credential_timestamp")
        return value

    @field_validator("last_refresh")
    @classmethod
    def aware_refresh(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("credential_timestamp")
        return value


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("credential_duplicate")
        result[key] = value
    return result


def _invalid_number(_value: str) -> object:
    raise ValueError("credential_number")


@dataclass(frozen=True, slots=True)
class Codex167CredentialCodec:
    expected_account: str = field(repr=False)
    expected_login_owner: str = field(repr=False)
    expected_oauth_issuer: str = field(repr=False)
    expected_oauth_client_id: str = field(repr=False)

    def __post_init__(self) -> None:
        for value in (
            self.expected_account,
            self.expected_login_owner,
            self.expected_oauth_issuer,
            self.expected_oauth_client_id,
        ):
            if not value or len(value) > MAX_BINDING_LENGTH or value.strip() != value:
                raise ValueError("Provisioned credential bindings required")

    def validate(self, encoded: bytes) -> CredentialDocument:
        try:
            if not 0 < len(encoded) <= MAX_CREDENTIAL_BYTES:
                raise ValueError("credential_size")
            value: object = json.loads(
                encoded.decode("utf-8"),
                object_pairs_hook=_closed_object,
                parse_constant=_invalid_number,
                parse_float=_invalid_number,
            )
            cache = _Cache.model_validate(value)
            if (
                cache.tokens.account_id != self.expected_account
                or cache.tokens.login_owner_id != self.expected_login_owner
                or cache.tokens.oauth_provenance.issuer != self.expected_oauth_issuer
                or cache.tokens.oauth_provenance.client_id != self.expected_oauth_client_id
            ):
                raise ValueError("credential_binding")
        except (ValueError, ValidationError, RecursionError):
            raise ValueError("credential_format_or_binding") from None
        # Preserve CLI serialization/refresh bytes; no JWT parsing or product-history rewrite.
        return CredentialDocument(self.expected_account, encoded)


def credential_binding_digest(codec: Codex167CredentialCodec) -> str:
    values = (
        codec.expected_account,
        codec.expected_login_owner,
        codec.expected_oauth_issuer,
        codec.expected_oauth_client_id,
    )
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()
