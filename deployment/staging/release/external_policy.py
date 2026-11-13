"""Host-only external acceptance admission; no SSH/CLI caller can activate a role."""

from __future__ import annotations

import copy
import json
import os
import stat
from dataclasses import dataclass, field, replace
from pathlib import Path

from deployment.staging.release.data import Object, obj, require, rows, text
from deployment.staging.release.external import AcceptedExternal
from deployment.staging.release.release import SCHEMA, Image
from deployment.staging.release.validation import check_sha

ACCEPTANCE_FILE = Path("/etc/peerly-release-ssh/external-acceptance.json")
ACCEPTANCE_MODE = 0o640
PRIVATE_MODE = 0o600
MAX_ACCEPTANCE = 1024 * 1024


def protected_read(path: Path) -> Object:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == 0
            and info.st_gid == os.getgid()
            and stat.S_IMODE(info.st_mode) == ACCEPTANCE_MODE,
            "external_acceptance_file_permissions",
        )
        raw = stream.read(MAX_ACCEPTANCE + 1)
        require(len(raw) <= MAX_ACCEPTANCE, "external_acceptance_file_size")
    return decode(raw)


def unique(pairs: list[tuple[str, object]]) -> Object:
    result: Object = {}
    for key, value in pairs:
        require(key not in result, "external_duplicate_json_key")
        result[key] = value
    return result


def decode(raw: bytes) -> Object:
    return obj(json.loads(raw, object_pairs_hook=unique))


def read_private(path: Path) -> Object:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == PRIVATE_MODE,
            "external_private_file_permissions",
        )
        raw = stream.read(MAX_ACCEPTANCE + 1)
        require(len(raw) <= MAX_ACCEPTANCE, "external_private_file_size")
    return decode(raw)


@dataclass(frozen=True, slots=True, repr=False)
class ExternalPolicy:
    accepted: AcceptedExternal
    service_spec: Object
    upgrade_source: str
    compatible_sources: frozenset[str]
    core_compatible_sources: frozenset[str]
    role_schema_evidence: Object
    admission_document: Object | None = field(default=None, repr=False)

    @classmethod
    def parse(cls, value: Object) -> ExternalPolicy:
        require(
            set(value)
            == {
                "version",
                "accepted",
                "service_spec",
                "upgrade_source",
                "compatible_sources",
                "core_compatible_sources",
                "role_schema_evidence",
            }
            and type(value["version"]) is int
            and value["version"] == 1,
            "external_policy_shape",
        )
        accepted = AcceptedExternal.parse(obj(value["accepted"]))
        spec = obj(value["service_spec"])
        require(
            spec.get("image") == accepted.config.get("Image")
            and type(obj(spec.get("deploy", {})).get("replicas")) is int
            and obj(spec.get("deploy", {})).get("replicas") == 1
            and type(spec.get("scale", 1)) is int
            and spec.get("scale", 1) == 1
            and obj(spec.get("deploy", {})).get("mode", "replicated") == "replicated"
            and not spec.get("profiles")
            and "build" not in spec
            and spec.get("pull_policy") == "never",
            "external_accepted_service_spec",
        )
        sources = frozenset(text(v) for v in rows(value["compatible_sources"]))
        require(bool(sources), "external_compatibility_missing")
        for source in sources:
            check_sha(source)
        current = text(obj(accepted.config["Labels"])["org.opencontainers.image.revision"])
        require(current in sources, "external_current_source_not_reviewed")
        upgrade = text(value["upgrade_source"])
        if upgrade:
            check_sha(upgrade)
            require(upgrade in sources, "external_upgrade_not_reviewed")
        core_sources = frozenset(text(v) for v in rows(value["core_compatible_sources"]))
        require(bool(core_sources), "external_core_compatibility_missing")
        for source in core_sources:
            check_sha(source)
        evidence = obj(value["role_schema_evidence"])
        require(set(evidence) == sources, "external_role_schema_evidence_sources")
        for raw in evidence.values():
            record = obj(raw)
            require(
                set(record)
                == {
                    "image",
                    "config",
                    "database_schema",
                    "image_schema_head",
                    "entrypoint",
                    "sinks",
                    "evidence_id",
                    "witness_kind",
                }
                and record["database_schema"] == SCHEMA
                and record["witness_kind"] == "immutable_image_role_compatibility"
                and record["entrypoint"] == "studymate.external_delivery_worker"
                and sorted(text(v) for v in rows(record["sinks"]))
                == sorted(text(v["sink"]) for v in accepted.destinations)
                and bool(text(record["image_schema_head"]))
                and bool(text(record["evidence_id"])),
                "external_role_schema_evidence",
            )
        return cls(accepted, spec, upgrade, sources, core_sources, evidence)

    def check_image(self, image: Image) -> None:
        require(image.sha in self.compatible_sources, "external_source_not_compatible")
        evidence = obj(self.role_schema_evidence[image.sha])
        require(
            evidence["image"] == image.reference and evidence["config"] == image.config,
            "external_role_schema_image_binding",
        )

    def check_current(self) -> None:
        if self.admission_document is not None:
            require(
                protected_read(ACCEPTANCE_FILE) == self.admission_document,
                "external_acceptance_changed_before_write",
            )


def policy() -> ExternalPolicy | None:
    try:
        value = protected_read(ACCEPTANCE_FILE)
    except FileNotFoundError:
        return None
    return replace(ExternalPolicy.parse(value), admission_document=copy.deepcopy(value))


def save_private(path: Path, value: Object) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(value, stream, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)


def sync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
