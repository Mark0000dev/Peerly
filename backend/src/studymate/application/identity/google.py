from dataclasses import dataclass, field
from typing import Protocol

from studymate.domain.membership import GoogleIdentity

MAX_AUTHORIZATION_CODE_LENGTH = 2048


class GoogleUnavailableError(Exception):
    """Provider unavailable; details and token responses must not reach users."""


class GoogleRejectedError(Exception):
    """Invalid authorization or assertion; a new login flow is required."""


@dataclass(frozen=True, slots=True)
class GoogleAuthorization:
    state: str = field(repr=False)
    nonce: str = field(repr=False)
    verifier: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class GoogleCode:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not self.value
            or len(self.value) > MAX_AUTHORIZATION_CODE_LENGTH
            or not self.value.isascii()
        ):
            raise GoogleRejectedError


class GoogleProvider(Protocol):
    async def authorization_url(self, authorization: GoogleAuthorization) -> str: ...

    async def exchange(
        self, code: GoogleCode, authorization: GoogleAuthorization
    ) -> GoogleIdentity: ...
