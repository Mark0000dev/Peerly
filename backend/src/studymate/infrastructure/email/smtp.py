import ssl
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime
from typing import Literal
from uuid import UUID

import aiosmtplib

from studymate.application.identity.email_delivery import (
    PermanentEmailError,
    TransientEmailError,
    VerificationEmail,
)
from studymate.infrastructure.email.reply_to import require_reply_to

SMTP_TRANSIENT_MIN = 400
SMTP_PERMANENT_MIN = 500


@dataclass(frozen=True, slots=True)
class SmtpConfiguration:
    hostname: str
    port: int
    username: str = field(repr=False)
    password: str = field(repr=False)
    sender: str
    mode: Literal["starttls", "tls"] = "starttls"
    reply_to: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.reply_to is not None:
            require_reply_to(self.reply_to)


@dataclass(frozen=True, slots=True)
class SmtpEmailSender:
    configuration: SmtpConfiguration
    tls_context: ssl.SSLContext

    async def send(self, message: VerificationEmail, delivery_id: UUID) -> None:
        configuration = self.configuration
        domain = configuration.sender.rpartition("@")[2]
        mail = EmailMessage()
        mail["From"] = configuration.sender
        if configuration.reply_to is not None:
            mail["Reply-To"] = configuration.reply_to
        mail["To"] = message.email.value
        mail["Subject"] = "Peerly: verify your APU student email"
        mail["Date"] = format_datetime(datetime.now(UTC))
        mail["Message-ID"] = f"<{delivery_id}@{domain}>"
        mail.set_content(
            f"Your Peerly student email verification code is: {message.code.value}\n\n"
            "This code expires in 10 minutes. If you did not request it, ignore this email.\n"
        )
        try:
            await aiosmtplib.send(
                mail,
                hostname=configuration.hostname,
                port=configuration.port,
                username=configuration.username,
                password=configuration.password,
                sender=configuration.sender,
                recipients=[message.email.value],
                use_tls=configuration.mode == "tls",
                start_tls=configuration.mode == "starttls",
                validate_certs=True,
                tls_context=self.tls_context,
                timeout=5,
                local_hostname=domain,
            )
        except aiosmtplib.SMTPRecipientsRefused as error:
            if any(
                SMTP_TRANSIENT_MIN <= item.code < SMTP_PERMANENT_MIN for item in error.recipients
            ):
                raise TransientEmailError from None
            raise PermanentEmailError from None
        except aiosmtplib.SMTPResponseException as error:
            if SMTP_TRANSIENT_MIN <= error.code < SMTP_PERMANENT_MIN:
                raise TransientEmailError from None
            raise PermanentEmailError from None
        except aiosmtplib.SMTPNotSupported:
            raise PermanentEmailError from None
        except (aiosmtplib.SMTPException, OSError):
            raise TransientEmailError from None
