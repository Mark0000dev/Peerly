"""Closed offline JSON schema and bounded local-file decoding; no settings or database."""

import asyncio
import json
import os
import stat
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError

from studymate.domain.bootstrap_data.inputs import (
    MAX_CATALOGUE_SUBJECTS,
    MAX_INPUT_BYTES,
    MAX_POLICY_CONTENT,
    MAX_POLICY_TITLE,
    AuthoredPolicy,
    AuthoredSubject,
    BootstrapBatch,
    CatalogueManifest,
)
from studymate.domain.catalogue import MAX_SUBJECT_ALIASES, MAX_SUBJECT_LABEL
from studymate.domain.registration import PolicyKind, PolicyVersion


class BootstrapInputCode(StrEnum):
    INPUT_SIZE = "input_size"
    INVALID_UTF8 = "invalid_utf8"
    INVALID_INPUT = "invalid_input"
    DUPLICATE_JSON_KEY = "duplicate_json_key"
    INVALID_JSON_NUMBER = "invalid_json_number"
    INPUT_FILE = "input_file"


class BootstrapInputError(Exception):
    """Safe finite input error, without offending file/content values."""

    def __init__(self, code: BootstrapInputCode) -> None:
        super().__init__(code.value)
        self.code = code


class ClosedInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class PolicyInput(ClosedInput):
    kind: PolicyKind
    version: Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")]
    title: Annotated[StrictStr, Field(min_length=1, max_length=MAX_POLICY_TITLE)]
    content: Annotated[StrictStr, Field(min_length=1, max_length=MAX_POLICY_CONTENT)]


class SubjectInput(ClosedInput):
    id: UUID
    name: Annotated[StrictStr, Field(min_length=1, max_length=MAX_SUBJECT_LABEL)]
    aliases: tuple[Annotated[StrictStr, Field(min_length=1, max_length=MAX_SUBJECT_LABEL)], ...] = (
        Field(max_length=MAX_SUBJECT_ALIASES)
    )


class CatalogueInput(ClosedInput):
    version: Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9._-]{1,64}$")]
    subjects: tuple[SubjectInput, ...] = Field(min_length=1, max_length=MAX_CATALOGUE_SUBJECTS)


class BootstrapInput(ClosedInput):
    schema_version: Annotated[StrictInt, Field(ge=1, le=1)]
    policies: tuple[PolicyInput, ...] = Field(max_length=2)
    catalogue: CatalogueInput | None

    def batch(self) -> BootstrapBatch:
        policies = tuple(
            AuthoredPolicy(policy.kind, PolicyVersion(policy.version), policy.title, policy.content)
            for policy in self.policies
        )
        catalogue = (
            None
            if self.catalogue is None
            else CatalogueManifest(
                self.catalogue.version,
                tuple(
                    AuthoredSubject(subject.id, subject.name, subject.aliases)
                    for subject in self.catalogue.subjects
                ),
            )
        )
        return BootstrapBatch(policies, catalogue)


def closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BootstrapInputError(BootstrapInputCode.DUPLICATE_JSON_KEY)
        result[key] = value
    return result


def invalid_number(_value: str) -> object:
    # This format has only one numeric field: integer schema_version1.
    raise BootstrapInputError(BootstrapInputCode.INVALID_JSON_NUMBER)


def parse_input(data: bytes) -> BootstrapBatch:
    if not 1 <= len(data) <= MAX_INPUT_BYTES:
        raise BootstrapInputError(BootstrapInputCode.INPUT_SIZE)
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise BootstrapInputError(BootstrapInputCode.INVALID_UTF8) from None
    try:
        value: object = json.loads(
            text,
            object_pairs_hook=closed_object,
            parse_constant=invalid_number,
            parse_float=invalid_number,
        )
        return BootstrapInput.model_validate(value).batch()
    except BootstrapInputError:
        raise
    except (ValueError, ValidationError, RecursionError):
        raise BootstrapInputError(BootstrapInputCode.INVALID_INPUT) from None


def read_regular_file(path: Path) -> bytes:
    # NONBLOCK prevents opening an attacker-supplied FIFO from stalling the executor.
    # A regular file is then read once with an explicit byte cap, including growth races.
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(descriptor, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT_BYTES:
                raise BootstrapInputError(BootstrapInputCode.INPUT_FILE)
            data = source.read(MAX_INPUT_BYTES + 1)
    except OSError:
        raise BootstrapInputError(BootstrapInputCode.INPUT_FILE) from None
    return data


async def load_input(path: Path) -> BootstrapBatch:
    return parse_input(await asyncio.to_thread(read_regular_file, path))
