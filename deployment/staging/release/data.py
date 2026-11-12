"""Checked JSON boundaries; remote data never escapes as untyped dictionaries."""

from __future__ import annotations

import json
from typing import TypeGuard

type Object = dict[str, object]
HTTP_OK = 200
MAX_ASSETS = 4096
COMPOSE_TYPE = 2


class RejectedError(RuntimeError):
    """Safe fixed diagnostic code."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise RejectedError(code)


def is_object(value: object) -> TypeGuard[Object]:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def obj(value: object) -> Object:
    if not is_object(value):
        raise RejectedError("json_object")
    return value


def rows(value: object) -> list[object]:
    if not isinstance(value, list):
        raise RejectedError("json_array")
    return list(value)


def text(value: object) -> str:
    if not isinstance(value, str):
        raise RejectedError("json_string")
    return value


def integer(value: object) -> int:
    if type(value) is not int:
        raise RejectedError("json_integer")
    return value


def load(raw: str | bytes) -> Object:
    try:
        value: object = json.loads(raw)
        return obj(value)
    except (ValueError, UnicodeError):
        raise RejectedError("invalid_json") from None


def array(raw: str) -> list[Object]:
    try:
        value: object = json.loads(raw)
        return [obj(item) for item in rows(value)]
    except (ValueError, UnicodeError):
        raise RejectedError("invalid_json") from None
