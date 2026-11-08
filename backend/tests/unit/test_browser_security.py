import pytest

from studymate.application.identity.google import GoogleCode, GoogleRejectedError
from studymate.application.identity.sessions import SessionCredential
from studymate.infrastructure.security.browser_tokens import HmacBrowserTokenSigner
from studymate.presentation.browser import BrowserConfiguration


async def test_csrf_is_bound_to_credential_and_source_hash_has_separate_purpose() -> None:
    signer = HmacBrowserTokenSigner(bytes(range(32)))
    first = SessionCredential("a" * 43)
    second = SessionCredential("b" * 43)
    csrf = await signer.csrf_token(first)
    assert csrf != first.value
    assert await signer.valid_csrf(first, csrf)
    assert not await signer.valid_csrf(second, csrf)
    assert not await signer.valid_csrf(first, "")
    assert not await signer.valid_csrf(first, "\u212a")
    assert await signer.source_digest(first.value) != bytes.fromhex(csrf)
    assert await signer.source_digest("127.0.0.1") == await signer.source_digest("127.0.0.1")
    assert await signer.source_digest("127.0.0.2") != await signer.source_digest("127.0.0.1")


def test_browser_signing_key_is_required() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        HmacBrowserTokenSigner(b"")


@pytest.mark.parametrize(
    "origin", ["http://app.test", "https://app.test/path", "https://user:secret@app.test"]
)
def test_browser_origins_are_explicit_https_origins(origin: str) -> None:
    with pytest.raises(ValueError, match="HTTPS origins"):
        BrowserConfiguration(origin, frozenset({origin}))


def test_public_origin_must_be_in_trusted_set() -> None:
    with pytest.raises(ValueError, match="must be trusted"):
        BrowserConfiguration("https://app.test", frozenset({"https://other.test"}))


@pytest.mark.parametrize("code", ["", "x" * 2049, "\u212a"])
def test_google_callback_code_is_bounded(code: str) -> None:
    with pytest.raises(GoogleRejectedError):
        GoogleCode(code)
