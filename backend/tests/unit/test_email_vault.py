from uuid import uuid4

import pytest

from studymate.application.idempotency import IntentKey
from studymate.application.identity.email_delivery import DeliveryEnvelopeError
from studymate.application.identity.email_verification import VerificationCode
from studymate.domain.identity import StudentEmail
from studymate.infrastructure.security.email_vault import AeadEmailVault


@pytest.mark.parametrize("key", ["", "short", "x" * 129, "contains space", "\u212a" * 8])
def test_email_intent_key_is_bounded(key: str) -> None:
    with pytest.raises(ValueError, match="idempotency"):
        IntentKey(key)


@pytest.mark.parametrize(
    "code", ["", "12345", "1234567", "abcdef", "\uff11\uff12\uff13\uff14\uff15\uff16"]
)
def test_code_requires_six_ascii_digits(code: str) -> None:
    with pytest.raises(ValueError, match="six ASCII digits"):
        VerificationCode(code)


async def test_otp_digest_and_delivery_are_bound_to_challenge_and_secret_key() -> None:
    vault = AeadEmailVault(bytes(range(32)), bytes(range(32, 64)))
    first, second = uuid4(), uuid4()
    code = VerificationCode("123456")
    assert code.value not in repr(code)
    assert await vault.code_digest(first, code) == await vault.code_digest(first, code)
    assert await vault.code_digest(first, code) != await vault.code_digest(second, code)
    other = AeadEmailVault(bytes(reversed(range(32))), bytes(range(32, 64)))
    assert await vault.code_digest(first, code) != await other.code_digest(first, code)
    assert await vault.fingerprint(("verify", str(first), code.value)) != await vault.fingerprint(
        ("start", str(first), code.value)
    )
    generated = await vault.generate_code()
    assert generated.value.isascii()
    assert generated.value.isdecimal()
    email = StudentEmail("tp@mail.apu.edu.my")
    sealed = await vault.seal_delivery(first, email, code)
    opened = await vault.open_delivery(first, sealed)
    assert opened.email == email
    assert opened.code == code
    assert email.value not in repr(opened)
    with pytest.raises(DeliveryEnvelopeError):
        await vault.open_delivery(second, sealed)
    with pytest.raises(DeliveryEnvelopeError):
        await vault.open_delivery(first, b"truncated")


@pytest.mark.parametrize(
    ("code_key", "envelope_key"),
    [(b"", b""), (bytes(32), bytes(32)), (bytes(31), bytes(range(32)))],
)
def test_email_requires_distinct_valid_keys(code_key: bytes, envelope_key: bytes) -> None:
    with pytest.raises(ValueError, match="distinct 32-byte"):
        AeadEmailVault(code_key, envelope_key)
