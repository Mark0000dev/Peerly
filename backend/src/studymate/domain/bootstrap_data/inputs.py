"""Explicit authored reference data; no publication time or account authority in inputs."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from unicodedata import category
from uuid import UUID

from studymate.domain.catalogue import MAX_SUBJECT_ALIASES, Subject, subject_key, subject_label
from studymate.domain.registration import (
    PolicyKind,
    PolicyReference,
    PolicyVersion,
    PublishedPolicy,
)
from studymate.domain.time import require_aware

MAX_INPUT_BYTES = 2 * 1024 * 1024
MAX_POLICY_TITLE = 240
MAX_POLICY_CONTENT = 200_000
MAX_CATALOGUE_SUBJECTS = 5000
MAX_CATALOGUE_ALIASES = MAX_CATALOGUE_SUBJECTS * MAX_SUBJECT_ALIASES
SHA256_BYTES = 32


def authored_text(value: str, maximum: int, *, multiline: bool) -> None:
    allowed = {"\n", "\r", "\t"} if multiline else set()
    if (
        not value.strip()
        or len(value) > maximum
        or any(
            category(character) == "Cs"
            or (category(character) == "Cc" and character not in allowed)
            for character in value
        )
    ):
        raise ValueError("Authored text must be actual, bounded and valid Unicode")


@dataclass(frozen=True, slots=True)
class AuthoredPolicy:
    kind: PolicyKind
    version: PolicyVersion
    title: str = field(repr=False)
    content: str = field(repr=False)

    def __post_init__(self) -> None:
        authored_text(self.title, MAX_POLICY_TITLE, multiline=False)
        authored_text(self.content, MAX_POLICY_CONTENT, multiline=True)

    def publish(self, identity: UUID, at: datetime) -> PublishedPolicy:
        return PublishedPolicy(
            PolicyReference(identity, self.kind, self.version, at), self.title, self.content
        )


@dataclass(frozen=True, slots=True)
class AuthoredSubject:
    id: UUID
    name: str = field(repr=False)
    aliases: tuple[str, ...] = field(repr=False)

    def __post_init__(self) -> None:
        name = subject_label(self.name)
        aliases = tuple(subject_label(alias) for alias in self.aliases)
        keys = tuple(subject_key(alias) for alias in aliases)
        if (
            len(aliases) > MAX_SUBJECT_ALIASES
            or len(set(keys)) != len(keys)
            or subject_key(name) in keys
        ):
            raise ValueError("Authored subject aliases must be bounded and distinct")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "aliases", aliases)

    def create(self, at: datetime) -> Subject:
        return Subject(self.id, self.name, self.aliases, at)


@dataclass(frozen=True, slots=True)
class CatalogueManifest:
    version: str
    subjects: tuple[AuthoredSubject, ...] = field(repr=False)

    def __post_init__(self) -> None:
        PolicyVersion(self.version)
        if not 1 <= len(self.subjects) <= MAX_CATALOGUE_SUBJECTS:
            raise ValueError("Catalogue manifest is outside the bounded subject count")
        if len({subject.id for subject in self.subjects}) != len(self.subjects) or len(
            {subject_key(subject.name) for subject in self.subjects}
        ) != len(self.subjects):
            raise ValueError("Catalogue manifest requires distinct stable IDs and names")
        object.__setattr__(
            self, "subjects", tuple(sorted(self.subjects, key=lambda value: value.id.int))
        )
        if len(self.canonical_json.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError("Canonical catalogue manifest exceeds its bounded source size")

    @property
    def canonical_json(self) -> str:
        return json.dumps(
            {
                "schema_version": 1,
                "version": self.version,
                "subjects": [
                    {"id": str(subject.id), "name": subject.name, "aliases": list(subject.aliases)}
                    for subject in self.subjects
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def sha256(self) -> bytes:
        return hashlib.sha256(self.canonical_json.encode("utf-8")).digest()

    @property
    def alias_count(self) -> int:
        return sum(len(subject.aliases) for subject in self.subjects)


@dataclass(frozen=True, slots=True)
class BootstrapBatch:
    policies: tuple[AuthoredPolicy, ...] = field(repr=False)
    catalogue: CatalogueManifest | None = field(repr=False)

    def __post_init__(self) -> None:
        if not self.policies and self.catalogue is None:
            raise ValueError("Bootstrap input must explicitly request reference data")
        if len({policy.kind for policy in self.policies}) != len(self.policies):
            raise ValueError("One authored policy version per kind is allowed in a batch")


@dataclass(frozen=True, slots=True)
class CatalogueProvenance:
    version: str
    sha256: bytes = field(repr=False)
    canonical_json: str = field(repr=False)
    applied_at: datetime
    subject_count: int
    alias_count: int

    def __post_init__(self) -> None:
        PolicyVersion(self.version)
        require_aware(self.applied_at)
        encoded = self.canonical_json.encode("utf-8")
        if (
            not 1 <= self.subject_count <= MAX_CATALOGUE_SUBJECTS
            or not 0 <= self.alias_count <= self.subject_count * MAX_SUBJECT_ALIASES
            or not 1 <= len(encoded) <= MAX_INPUT_BYTES
            or len(self.sha256) != SHA256_BYTES
            or hashlib.sha256(encoded).digest() != self.sha256
        ):
            raise ValueError("Catalogue provenance must retain its bounded canonical source digest")
