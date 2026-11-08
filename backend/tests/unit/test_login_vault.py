from uuid import uuid4

import pytest

from studymate.application.identity.google import GoogleRejectedError
from studymate.infrastructure.security.login_vault import AeadLoginVault


async def test_login_secrets_are_random_and_encrypted_for_one_flow() -> None:
    vault = AeadLoginVault(bytes(range(32)))
    first = await vault.generate()
    second = await vault.generate()
    assert first != second
    assert first.authorization.nonce != second.authorization.nonce
    assert first.browser != second.browser
    assert await vault.session_credential() != first.browser
    identity = uuid4()
    sealed = await vault.seal(first.authorization, identity)
    assert first.authorization.verifier.encode() not in sealed
    assert await vault.open(sealed, identity) == first.authorization
    assert await vault.digest(first.browser.value) == await vault.digest(first.browser.value)
    assert await vault.digest(first.browser.value) != await vault.digest(second.browser.value)
    with pytest.raises(GoogleRejectedError):
        await vault.open(sealed, uuid4())
    with pytest.raises(GoogleRejectedError):
        await vault.open(sealed[:-1] + bytes([sealed[-1] ^ 1]), identity)
    with pytest.raises(GoogleRejectedError):
        await vault.open(b"truncated", identity)


def test_missing_or_invalid_encryption_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        AeadLoginVault(b"")
