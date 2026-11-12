"""Offline, untrusted header claims only; never cryptographic or delivery proof."""

import json
import re
import sys
from collections.abc import Mapping
from typing import BinaryIO

MAX_HEADER_BYTES = 65536
MAX_LINE_BYTES = 8192
AUTH_RESULTS = frozenset(
    {
        "pass",
        "fail",
        "softfail",
        "neutral",
        "none",
        "temperror",
        "permerror",
        "softpass",
        "bestguesspass",
    }
)
ASCII_SPACE = 32
ASCII_TAB = 9
ASCII_TILDE = 126
SAFE_FIELDS = {
    "scl": frozenset({"-1", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"}),
    "sfv": frozenset({"spm", "nspm", "skq", "sks", "ska", "skb", "skn", "ski", "skc"}),
    "cat": frozenset(
        {"none", "bulk", "spm", "hspm", "phsh", "hphsh", "spoof", "malw", "dimp", "uimp", "gimp"}
    ),
}


class InvalidHeadersError(ValueError):
    """Fixed public error; input content must never appear in exceptions."""


def read_headers(stream: BinaryIO) -> tuple[tuple[str, str], ...]:
    """Read one byte at a time, stopping before body; at most limit + 1 bytes.

    Caller must provide an unbuffered stream to prevent underlying read-ahead.
    Require a header/body separator, including for a header-only export.
    """
    lines: list[bytes] = []
    line = bytearray()
    total = 0
    while True:
        char = stream.read(1)
        total += len(char)
        if not char or total > MAX_HEADER_BYTES:
            raise InvalidHeadersError("invalid_or_oversized_headers")
        line.extend(char)
        if len(line) > MAX_LINE_BYTES:
            raise InvalidHeadersError("invalid_or_oversized_headers")
        if char == b"\n":
            value = bytes(line).removesuffix(b"\n").removesuffix(b"\r")
            line.clear()
            if not value:
                break
            if any(
                (byte < ASCII_SPACE and byte != ASCII_TAB) or byte > ASCII_TILDE for byte in value
            ):
                raise InvalidHeadersError("invalid_or_oversized_headers")
            lines.append(value)
    fields: list[tuple[str, str]] = []
    for raw in lines:
        if raw.startswith((b" ", b"\t")):
            if not fields:
                raise InvalidHeadersError("invalid_or_oversized_headers")
            name, previous = fields[-1]
            fields[-1] = (name, previous + " " + raw.decode("ascii").strip())
        else:
            name_bytes, separator, content = raw.partition(b":")
            if not separator or not re.fullmatch(rb"[!-9;-~]+", name_bytes):
                raise InvalidHeadersError("invalid_or_oversized_headers")
            fields.append((name_bytes.decode("ascii").lower(), content.decode("ascii").strip()))
    return tuple(fields)


def authentication_claims(value: str) -> dict[str, list[str]]:
    """Conservative subset: ignore segments containing comments or quoted strings.

    Keep conflicting and repeated methods. No authserv-id/domain/identity output.
    DMARC pass is only a header-reported alignment/authentication claim.
    """
    result: dict[str, list[str]] = {}
    # Refuse complex syntax rather than accidentally parsing text inside a comment.
    if any(character in value for character in '()"\\'):
        return result
    for segment in value.lower().split(";"):
        match = re.match(r"\s*(spf|dkim|dmarc|compauth)\s*=\s*([a-z]+)(?=\s|$)", segment)
        if match is None:
            continue
        method, outcome = match.groups()
        result.setdefault(method, []).append(outcome if outcome in AUTH_RESULTS else "unknown")
        if method == "dmarc":
            action = re.search(r"(?:^|\s)action=(none|quarantine|reject)(?=\s|$)", segment)
            if action is not None:
                result.setdefault("dmarc_action", []).append(action.group(1))
    return result


def filtering_claims(value: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for segment in value.lower().split(";"):
        key, separator, outcome = segment.strip().partition(":")
        if separator and key in SAFE_FIELDS:
            result.setdefault(key, []).append(outcome if outcome in SAFE_FIELDS[key] else "unknown")
    return result


def diagnose(stream: BinaryIO) -> Mapping[str, object]:
    """Emit fixed keys and allowlisted tokens only, never raw source strings."""
    authentication: list[dict[str, list[str]]] = []
    filtering: list[dict[str, list[str]]] = []
    for name, value in read_headers(stream):
        if name == "authentication-results":
            authentication.append(authentication_claims(value))
        elif name == "x-forefront-antispam-report":
            filtering.append(filtering_claims(value))
        elif name == "x-ms-exchange-organization-scl":
            filtering.append(filtering_claims("scl:" + value))
    return {
        "evidence": "untrusted_header_claims_only",
        "authentication": authentication,
        "filtering": filtering,
        "alignment": "dmarc_result_only_no_independent_domain_alignment_check",
        "delivery": "unknown_requires_recipient_evidence",
    }


def main() -> int:
    try:
        # FileIO bypasses sys.stdin.buffer prefetch: no body bytes are consumed.
        with open(sys.stdin.fileno(), "rb", buffering=0, closefd=False) as stream:
            report = diagnose(stream)
    except (InvalidHeadersError, OSError, ValueError):
        sys.stderr.write("invalid_or_unreadable_headers\n")
        return 2
    sys.stdout.write(json.dumps(dict(report), sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
