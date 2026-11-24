import re
from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MIN_PRINTABLE_ORD = 32
TIMEZONE_MAX = 100
ENDPOINT_MAX = 4096


class Platform(StrEnum):
    WEB = "web"
    IOS = "ios"
    ANDROID = "android"


@dataclass(frozen=True, slots=True)
class DeviceState:
    installation_id: UUID
    platform: Platform
    version: int
    enabled: bool
    timezone: str | None
    material_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class Capabilities:
    web: bool = False
    ios: bool = False
    android: bool = False
    vapid_public_key: str | None = None

    def supports(self, platform: Platform) -> bool:
        return {Platform.WEB: self.web, Platform.IOS: self.ios, Platform.ANDROID: self.android}[
            platform
        ]


@dataclass(frozen=True, slots=True)
class Registration:
    installation_id: UUID
    platform: Platform
    enabled: bool
    timezone: str | None
    endpoint: str | None = field(default=None, repr=False)
    p256dh: str | None = field(default=None, repr=False)
    auth: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.timezone is not None:
            if len(self.timezone) > TIMEZONE_MAX:
                raise ValueError("Invalid IANA timezone")
            try:
                ZoneInfo(self.timezone)
            except ZoneInfoNotFoundError:
                raise ValueError("Invalid IANA timezone") from None
        if not self.enabled:
            if any(value is not None for value in (self.endpoint, self.p256dh, self.auth)):
                raise ValueError("Disabled registration must not retain transport material")
            return
        if (
            self.endpoint is None
            or not 1 <= len(self.endpoint) <= ENDPOINT_MAX
            or any(
                character.isspace() or ord(character) < MIN_PRINTABLE_ORD
                for character in self.endpoint
            )
        ):
            raise ValueError("Transport endpoint required")
        if self.platform == Platform.WEB:
            url = urlsplit(self.endpoint)
            if (
                url.scheme != "https"
                or not url.hostname
                or url.username
                or url.password
                or url.fragment
                or url.port not in (None, 443)
            ):
                raise ValueError("HTTPS push endpoint required")
            if self.p256dh is None or self.auth is None:
                raise ValueError("Web push keys required")
        elif (
            self.platform == Platform.IOS
            and re.fullmatch(r"[0-9a-fA-F]{16,512}", self.endpoint) is None
        ) or (
            self.platform == Platform.ANDROID
            and re.fullmatch(r"[A-Za-z0-9:_-]{1,4096}", self.endpoint) is None
        ):
            raise ValueError("Invalid native transport token")
        elif self.p256dh is not None or self.auth is not None:
            raise ValueError("Native registration uses its actual platform token")
