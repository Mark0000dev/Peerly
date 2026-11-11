"""Immutable exact destination revisions; credentials never enter target fingerprints."""

import hashlib
import json
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import UUID

from studymate.domain.external_delivery.delivery import DestinationRef
from studymate.domain.external_delivery.sources import Sink

MIN_VISIBLE_ASCII = 33
DELETE_ASCII = 127
MAX_CHAT_ID = (1 << 52) - 1


def require_origin(value: str) -> None:
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme == "https"
            and bool(parts.hostname)
            and parts.port != 0
            and parts.username is None
            and parts.password is None
            and not parts.path
            and not parts.query
            and not parts.fragment
            and not any(
                character.isspace()
                or ord(character) < MIN_VISIBLE_ASCII
                or ord(character) == DELETE_ASCII
                for character in value
            )
            and "\\" not in value
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("External destination requires a configured HTTPS origin")


@dataclass(frozen=True, slots=True)
class UmamiConfig:
    destination: DestinationRef
    origin: str
    website_id: UUID

    def __post_init__(self) -> None:
        require_origin(self.origin)
        if self.destination.sink != Sink.UMAMI:
            raise ValueError("Umami destination requires its registered sink")


@dataclass(frozen=True, slots=True)
class TelegramConfig:
    destination: DestinationRef
    chat_id: int
    operator_origin: str
    token: str | None = field(default=None, repr=False)
    topic_id: int | None = None

    def __post_init__(self) -> None:
        require_origin(self.operator_origin)
        if self.destination.sink != Sink.TELEGRAM_SUPPORT:
            raise ValueError("Support Telegram requires its registered sink")
        if type(self.chat_id) is not int or not 0 < abs(self.chat_id) <= MAX_CHAT_ID:
            raise ValueError("Telegram requires an actual numeric chat identifier")
        if self.topic_id is not None and (
            type(self.topic_id) is not int or not 1 <= self.topic_id <= MAX_CHAT_ID
        ):
            raise ValueError("Telegram topic requires an actual positive identifier")


type DestinationConfig = UmamiConfig | TelegramConfig


def target_fingerprint(configuration: DestinationConfig) -> bytes:
    fields: dict[str, str | int | None] = {
        "schema_version": 1,
        "sink": configuration.destination.sink.value,
    }
    if isinstance(configuration, UmamiConfig):
        fields.update(origin=configuration.origin, website_id=str(configuration.website_id))
    else:
        fields.update(
            chat_id=configuration.chat_id,
            topic_id=configuration.topic_id,
            operator_origin=configuration.operator_origin,
        )
    return hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).digest()
