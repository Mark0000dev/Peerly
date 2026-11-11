import asyncio
import ssl
from dataclasses import replace
from email import policy
from email.headerregistry import AddressHeader
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import Literal
from uuid import uuid4

import aiosmtplib
import pytest

from studymate.application.identity.email_delivery import (
    PermanentEmailError,
    TransientEmailError,
    VerificationEmail,
)
from studymate.application.identity.email_verification import VerificationCode
from studymate.domain.identity import StudentEmail
from studymate.infrastructure.email.smtp import SmtpConfiguration, SmtpEmailSender


@pytest.fixture(scope="module")
def tls_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def configuration(mode: Literal["starttls", "tls"] = "starttls") -> SmtpConfiguration:
    return SmtpConfiguration(
        "smtp.example.test",
        587,
        "synthetic-user",
        "synthetic-password",
        "verify@example.test",
        mode,
    )


@pytest.mark.parametrize("mode", ["starttls", "tls"])
async def test_smtp_uses_verified_tls_one_recipient_and_stable_message_id(
    monkeypatch: pytest.MonkeyPatch,
    tls_context: ssl.SSLContext,
    mode: Literal["starttls", "tls"],
) -> None:
    sent: list[str] = []

    async def send(
        message: EmailMessage, **options: object
    ) -> tuple[dict[str, aiosmtplib.SMTPResponse], str]:
        assert options["use_tls"] == (mode == "tls")
        assert options["start_tls"] == (mode == "starttls")
        assert options["validate_certs"] is True
        assert options["tls_context"] is tls_context
        assert options["recipients"] == ["tp@mail.apu.edu.my"]
        assert options["local_hostname"] == "example.test"
        body: object = message.get_content()
        assert isinstance(body, str)
        assert "123456" in body
        assert "10 minutes" in body
        sent.append(str(message["Message-ID"]))
        return {}, "ok"

    monkeypatch.setattr(aiosmtplib, "send", send)
    sender = SmtpEmailSender(configuration(mode), tls_context)
    message = VerificationEmail(StudentEmail("tp@mail.apu.edu.my"), VerificationCode("123456"))
    delivery_id = uuid4()
    await sender.send(message, delivery_id)
    await sender.send(message, delivery_id)
    assert sent == [f"<{delivery_id}@example.test>", f"<{delivery_id}@example.test>"]
    assert "synthetic-password" not in repr(sender)
    assert "synthetic-user" not in repr(sender)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (aiosmtplib.SMTPDataError(451, "private-provider-response"), TransientEmailError),
        (aiosmtplib.SMTPDataError(550, "private-provider-response"), PermanentEmailError),
        (
            aiosmtplib.SMTPRecipientsRefused(
                [aiosmtplib.SMTPRecipientRefused(450, "private-response", "tp@mail.apu.edu.my")]
            ),
            TransientEmailError,
        ),
        (
            aiosmtplib.SMTPRecipientsRefused(
                [aiosmtplib.SMTPRecipientRefused(550, "private-response", "tp@mail.apu.edu.my")]
            ),
            PermanentEmailError,
        ),
        (aiosmtplib.SMTPNotSupported("TLS unsupported"), PermanentEmailError),
        (aiosmtplib.SMTPServerDisconnected("private-provider-response"), TransientEmailError),
        (OSError("private-provider-response"), TransientEmailError),
    ],
)
async def test_smtp_errors_are_classified_without_private_provider_details(
    monkeypatch: pytest.MonkeyPatch,
    tls_context: ssl.SSLContext,
    error: Exception,
    expected: type[Exception],
) -> None:
    async def fail(
        _message: EmailMessage, **_options: object
    ) -> tuple[dict[str, aiosmtplib.SMTPResponse], str]:
        raise error

    monkeypatch.setattr(aiosmtplib, "send", fail)
    with pytest.raises(expected) as raised:
        await SmtpEmailSender(configuration(), tls_context).send(
            VerificationEmail(StudentEmail("tp@mail.apu.edu.my"), VerificationCode("123456")),
            uuid4(),
        )
    assert raised.value.args == ()
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


async def test_smtp_preserves_cancellation(
    monkeypatch: pytest.MonkeyPatch, tls_context: ssl.SSLContext
) -> None:
    async def cancelled(
        _message: EmailMessage, **_options: object
    ) -> tuple[dict[str, aiosmtplib.SMTPResponse], str]:
        raise asyncio.CancelledError

    monkeypatch.setattr(aiosmtplib, "send", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await SmtpEmailSender(configuration(), tls_context).send(
            VerificationEmail(StudentEmail("tp@mail.apu.edu.my"), VerificationCode("123456")),
            uuid4(),
        )


@pytest.mark.parametrize("reply_to", [None, "support@example.test"])
async def test_reply_header_is_optional_and_never_changes_envelope_or_student_recipient(
    monkeypatch: pytest.MonkeyPatch,
    tls_context: ssl.SSLContext,
    reply_to: str | None,
) -> None:
    delivered: list[EmailMessage] = []

    async def send(
        message: EmailMessage,
        **options: object,
    ) -> tuple[dict[str, aiosmtplib.SMTPResponse], str]:
        delivered.append(message)
        assert options["sender"] == "verify@example.test"
        assert options["recipients"] == ["tp@mail.apu.edu.my"]
        return {}, "controlled"

    monkeypatch.setattr(aiosmtplib, "send", send)
    sender = SmtpEmailSender(replace(configuration(), reply_to=reply_to), tls_context)
    await sender.send(
        VerificationEmail(StudentEmail("tp@mail.apu.edu.my"), VerificationCode("123456")), uuid4()
    )
    assert len(delivered) == 1
    message = delivered[0]
    assert str(message["From"]) == "Peerly <verify@example.test>"
    assert str(message["To"]) == "tp@mail.apu.edu.my"
    if reply_to is None:
        assert "Reply-To" not in message
    else:
        assert str(message["Reply-To"]) == reply_to
        assert len(message.get_all("Reply-To", [])) == 1


@pytest.mark.parametrize("reply_to", [None, "support@example.test"])
async def test_wire_message_identifies_independent_peerly_and_mailbox_only_purpose(
    monkeypatch: pytest.MonkeyPatch,
    tls_context: ssl.SSLContext,
    reply_to: str | None,
) -> None:
    messages: list[EmailMessage] = []
    bare_sender = "verify+codes@sub.example.test"

    async def capture(
        message: EmailMessage, **options: object
    ) -> tuple[dict[str, aiosmtplib.SMTPResponse], str]:
        assert options["sender"] == bare_sender
        assert options["recipients"] == ["tp@mail.apu.edu.my"]
        messages.append(
            BytesParser(policy=policy.default).parsebytes(message.as_bytes(policy=policy.SMTP))
        )
        return {}, "controlled"

    monkeypatch.setattr(aiosmtplib, "send", capture)
    sender = SmtpEmailSender(
        replace(configuration(), sender=bare_sender, reply_to=reply_to), tls_context
    )
    delivery_id = uuid4()
    message = VerificationEmail(StudentEmail("tp@mail.apu.edu.my"), VerificationCode("123456"))
    await sender.send(message, delivery_id)
    await sender.send(message, delivery_id)
    for wire in messages:
        header = wire["From"]
        assert isinstance(header, AddressHeader)
        assert len(header.addresses) == 1
        assert header.addresses[0].display_name == "Peerly"
        assert header.addresses[0].addr_spec == bare_sender
        assert str(wire["Message-ID"]) == f"<{delivery_id}@sub.example.test>"
        assert parsedate_to_datetime(str(wire["Date"])).utcoffset() is not None
        assert wire.get_content_type() == "text/plain"
        assert not wire.is_multipart()
        assert "Cc" not in wire
        assert "Bcc" not in wire
        assert (str(wire["Reply-To"]) if reply_to else None) == reply_to
        body: object = wire.get_content()
        assert isinstance(body, str)
        assert "123456" in body
        assert "confirm access to your APU student mailbox" in body
        assert "independent student project" in body
        assert "latest requested code" in body
        assert "10 minutes after the request" in body
        assert "If you did not request it, ignore this email" in body
        assert "http://" not in body
        assert "https://" not in body
