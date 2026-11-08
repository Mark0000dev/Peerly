"""Bounded Unicode plain text; errors never include the submitted value."""

from unicodedata import category


def plain_text(
    value: str,
    *,
    minimum: int,
    maximum: int,
    multiline: bool = False,
    collapse_spaces: bool = False,
) -> str:
    normalized = " ".join(value.split()) if collapse_spaces else value.strip()
    if not minimum <= len(normalized) <= maximum:
        raise ValueError("Text length is outside the allowed range")
    allowed_controls = {"\n", "\t"} if multiline else set()
    if any(
        category(character) == "Cs"
        or (category(character) == "Cc" and character not in allowed_controls)
        for character in normalized
    ):
        raise ValueError("Text contains unsupported control characters")
    return normalized


def optional_text(value: str | None, *, maximum: int, multiline: bool = False) -> str | None:
    if value is None or not value.strip():
        return None
    return plain_text(value, minimum=1, maximum=maximum, multiline=multiline)
