from datetime import UTC, datetime
from uuid import uuid4

import pytest

from studymate.application.support.cases import SupportCredential, SupportUnavailableError
from studymate.domain.support.cases import (
    SupportContent,
    SupportReceipt,
    SupportStatus,
    SupportTopic,
)
from studymate.infrastructure.support.proofs import OpaqueSupportProofs


@pytest.mark.parametrize("address", ["", "a@", "a@b", "a\r\n@b.test", " a@b.test", "a@@b.test"])
def test_reply_address_rejects_missing_or_header_injected_addresses(address: str) -> None:
    with pytest.raises(ValueError, match="reply address"):
        SupportContent(SupportTopic.CANNOT_SIGN_IN, address, "Cannot sign in")


@pytest.mark.parametrize(
    ("message", "details"),
    [(" ", None), ("x" * 4001, None), ("x", " "), ("x", "y" * 2001), ("x\x00", None)],
)
def test_private_content_is_bounded(message: str, details: str | None) -> None:
    with pytest.raises(ValueError, match=r"Support|support|Optional"):
        SupportContent(SupportTopic.OTHER, "reply@example.test", message, details)


def test_content_and_proof_repr_never_contain_private_values() -> None:
    content = SupportContent(
        SupportTopic.DELETED_ACCOUNT, "private@example.test", "private message", "private details"
    )
    assert "private" not in repr(content)
    proofs = OpaqueSupportProofs()
    first, second = proofs.issue(), proofs.issue()
    assert first != second
    assert first.value not in repr(first)
    assert proofs.digest(first) != proofs.digest(second)
    assert proofs.digest(SupportCredential(first.value)) == proofs.digest(first)
    with pytest.raises(SupportUnavailableError):
        SupportCredential("case-uuid-is-not-a-proof")


def test_receipt_requires_actual_aware_ordered_revision() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match=r"Support|support|Optional"):
        SupportReceipt(uuid4(), SupportStatus.RECEIVED, 0, now, now)


@pytest.mark.parametrize("codepoint", [0xD800, 0xDFFF, 0x7F, 0x85, 0])
@pytest.mark.parametrize("field", ["reply_address", "message", "details"])
def test_surrogates_and_controls_are_rejected_before_encoding(field: str, codepoint: int) -> None:
    character = chr(codepoint)
    address = f"reply{character}@example.test" if field == "reply_address" else "reply@example.test"
    message = f"message{character}" if field == "message" else "message"
    details = f"details{character}" if field == "details" else None
    with pytest.raises(ValueError, match=r"reply address|unsupported control"):
        SupportContent(SupportTopic.OTHER, address, message, details)


def test_allowed_multiline_unicode_content_is_preserved_exactly() -> None:
    message = "  Context\r\n\t字 e\u0301 😀  "
    details = "\tDetails\r\n  "
    content = SupportContent(SupportTopic.OTHER, "reply@example.test", message, details)
    assert content.message == message
    assert content.details == details
