from dataclasses import replace

import pytest
from pydantic import SecretStr, ValidationError

from studymate.config import SmtpDeliveryConfiguration
from studymate.infrastructure.email.reply_to import require_reply_to
from tests.unit.test_smtp_sender import configuration


def smtp(reply_to: str | None = None) -> SmtpDeliveryConfiguration:
    return SmtpDeliveryConfiguration(
        hostname="smtp.example.test",
        port=587,
        username=SecretStr("synthetic-user"),
        password=SecretStr("synthetic-password"),
        sender="verify@example.test",
        reply_to=reply_to,
    )


@pytest.mark.parametrize(
    "address", ["support@example.test", "Support+Replies@sub-domain.example.test", "a@b.test"]
)
def test_optional_reply_address_is_preserved_without_normalizing_mailbox_identity(
    address: str,
) -> None:
    assert require_reply_to(address) == address
    assert smtp(address).reply_to == address
    assert replace(configuration(), reply_to=address).reply_to == address
    assert address not in repr(smtp(address))
    assert address not in repr(replace(configuration(), reply_to=address))


def test_unset_reply_address_remains_absent_from_configuration() -> None:
    assert smtp().reply_to is None
    assert configuration().reply_to is None


@pytest.mark.parametrize(
    "address",
    [
        "",
        "support",
        "support@localhost",
        " support@example.test",
        "support@example.test ",
        "Peerly <support@example.test>",
        "a@example.test,b@example.test",
        "a@@example.test",
        "a..b@example.test",
        ".a@example.test",
        "a.@example.test",
        "a@-example.test",
        "a@example-.test",
        "a@example..test",
        "a@" + "x" * 64 + ".test",
        "a" * 65 + "@example.test",
        "a@" + "x." * 124 + "example.test",
        "студент@example.test",
        "private-inbox@example.test\r\nBcc: other@example.test",
        "a@example.test\x00",
    ],
)
def test_config_and_direct_sender_reject_invalid_or_multiple_reply_mailboxes(address: str) -> None:
    with pytest.raises(ValidationError) as error:
        smtp(address)
    assert "private-inbox" not in str(error.value)
    with pytest.raises(ValueError, match="one bare ASCII"):
        replace(configuration(), reply_to=address)
