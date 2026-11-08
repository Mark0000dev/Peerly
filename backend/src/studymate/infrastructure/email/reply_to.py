"""One bare mailbox for the optional SMTP reply header; validation never uses DNS."""

import re

MAX_ADDRESS_LENGTH = 254
MAX_LOCAL_LENGTH = 64
MIN_DOMAIN_LABELS = 2
_LOCAL = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*")
_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


def require_reply_to(value: str) -> str:
    local, separator, domain = value.partition("@")
    labels = domain.split(".")
    if (
        not value.isascii()
        or len(value) > MAX_ADDRESS_LENGTH
        or separator != "@"
        or len(local) > MAX_LOCAL_LENGTH
        or not _LOCAL.fullmatch(local)
        or len(labels) < MIN_DOMAIN_LABELS
        or any(not _LABEL.fullmatch(label) for label in labels)
    ):
        raise ValueError("SMTP Reply-To must be one bare ASCII email address with a DNS domain")
    return value
