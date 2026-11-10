import json

import pytest

from studymate.infrastructure.ai.runtime.credential_codec import Codex167CredentialCodec


def encoded(*, refresh: str = "synthetic-refresh") -> bytes:
    return json.dumps(
        {
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": None,
            "tokens": {
                "id_token": "synthetic.opaque.signature",
                "access_token": "synthetic-access",
                "refresh_token": refresh,
                "account_id": "synthetic-account",
                "login_owner_id": "synthetic-login",
                "oauth_provenance": {"issuer": "synthetic-issuer", "client_id": "synthetic-client"},
            },
            "last_refresh": "2026-11-09T00:00:00Z",
        }
    ).encode()


def codec() -> Codex167CredentialCodec:
    return Codex167CredentialCodec(
        "synthetic-account", "synthetic-login", "synthetic-issuer", "synthetic-client"
    )


def test_exact_cache_rotation_preserves_opaque_bytes_without_jwt_identity_trust() -> None:
    original = encoded()
    rotated = encoded(refresh="synthetic-rotated")
    assert codec().validate(original).encoded == original
    assert codec().validate(rotated).encoded == rotated
    assert codec().validate(rotated).account_binding == "synthetic-account"
    assert "synthetic-access" not in repr(codec().validate(original))


@pytest.mark.parametrize(
    "bad",
    [
        b"{}",
        b"[]",
        b"not-json",
        b'{"auth_mode":"chatgpt","auth_mode":"chatgpt"}',
        encoded().replace(b'"OPENAI_API_KEY": null', b'"OPENAI_API_KEY": "synthetic-key"'),
        encoded().replace(b"synthetic-login", b"synthetic-other-owner"),
        encoded().replace(b"synthetic-account", b"synthetic-other-account"),
        encoded().replace(b"synthetic-issuer", b"synthetic-other-issuer"),
        encoded().replace(b'"auth_mode": "chatgpt"', b'"auth_mode": "api"'),
        encoded()[:-1] + b',"private_history":"SYNTHETIC_PRIVATE"}',
    ],
)
def test_non_subscription_unknown_and_changed_bindings_fail_safely(bad: bytes) -> None:
    with pytest.raises(ValueError, match="credential_format_or_binding") as error:
        codec().validate(bad)
    assert "SYNTHETIC_PRIVATE" not in str(error.value)
