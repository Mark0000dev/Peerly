"""Read-only installed-SDK/license provenance; never installs or accepts terms."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NoReturn
from xml.etree import ElementTree as ET
from xml.parsers import expat

EXPECTED_ARGUMENTS = 2
MAX_XML = 2 * 1024 * 1024
MAX_RECORD = 64 * 1024
LICENSE_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
HASH_LINE = re.compile(r"[0-9a-f]{40}\Z")


class SDKPreflightError(ValueError):
    """Fixed safe diagnostic code; never includes license contents or raw errors."""


@dataclass(frozen=True, slots=True)
class LicenseReport:
    identifier: str
    content_sha1: str
    content_sha256: str
    record_sha256: str | None
    recorded_hashes: tuple[str, ...]
    accepted: bool
    error: str | None


@dataclass(frozen=True, slots=True)
class PackageReport:
    package: str
    metadata_sha256: str | None
    properties_sha256: str | None
    license_refs: tuple[str, ...]
    licenses: tuple[LicenseReport, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SDKReport:
    root: str
    platform: str
    build_tools: str
    packages: tuple[PackageReport, ...]
    accepted: bool
    errors: tuple[str, ...]


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def bounded_read(path: Path, root: Path, limit: int) -> bytes:
    if not path.resolve().is_relative_to(root):
        raise SDKPreflightError("path_outside_sdk")
    try:
        with path.open("rb") as stream:
            value = stream.read(limit + 1)
    except OSError:
        raise SDKPreflightError("missing_or_unreadable_file") from None
    if len(value) > limit:
        raise SDKPreflightError("input_too_large")
    return value


def parse_metadata(value: bytes) -> ET.Element:
    if len(value) > MAX_XML:
        raise SDKPreflightError("input_too_large")
    try:
        content = value.decode("utf-8-sig")
    except UnicodeError:
        raise SDKPreflightError("metadata_not_utf8") from None
    if "\x00" in content or any(token in content.upper() for token in ("<!DOCTYPE", "<!ENTITY")):
        raise SDKPreflightError("xml_declarations_forbidden")

    def reject_declaration(*_arguments: object) -> NoReturn:
        raise SDKPreflightError("xml_declarations_forbidden")

    builder = ET.TreeBuilder()
    parser = expat.ParserCreate(encoding="UTF-8", namespace_separator="}")
    parser.StartElementHandler = builder.start
    parser.EndElementHandler = builder.end
    parser.CharacterDataHandler = builder.data
    parser.StartDoctypeDeclHandler = reject_declaration
    parser.EntityDeclHandler = reject_declaration
    parser.ExternalEntityRefHandler = reject_declaration
    if not parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER):
        raise SDKPreflightError("external_entity_policy_unavailable")
    try:
        parser.Parse(content, True)
        return builder.close()
    except expat.ExpatError:
        raise SDKPreflightError("malformed_metadata") from None


def local_name(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def license_report(root: Path, identifier: str, content: str) -> LicenseReport:
    # Android repository License.getLicenseHash hashes getValue UTF-8 EXACTLY.
    # XML entities/newlines are decoded by XML parsing; never strip/collapse text.
    encoded = content.encode("utf-8")
    required = hashlib.sha1(encoded, usedforsecurity=False).hexdigest()
    record_hash: str | None = None
    recorded: tuple[str, ...] = ()
    try:
        value = bounded_read(root / "licenses" / identifier, root, MAX_RECORD)
        record_hash = sha256(value)
        lines = re.split(r"\r\n|\r|\n", value.decode("utf-8"))
        # SDK manager compares complete lines exactly, without trim/case folding.
        recorded = tuple(sorted({line for line in lines if HASH_LINE.fullmatch(line)}))
        accepted = required in lines
        error = None if accepted else "installed_license_not_recorded_as_accepted"
    except UnicodeError:
        accepted, error = False, "record_not_utf8"
    except SDKPreflightError as failure:
        accepted, error = False, str(failure)
    return LicenseReport(
        identifier, required, sha256(encoded), record_hash, recorded, accepted, error
    )


def check_platform_api(package: str, installed: ET.Element) -> None:
    if package == "platforms;android-37.0":
        levels = [node.text for node in installed.iter() if local_name(node) == "api-level"]
        previews = [
            node.text for node in installed.iter() if local_name(node) == "codename" and node.text
        ]
        if levels != ["37.0"] or previews:
            raise SDKPreflightError("installed_platform_api_mismatch")


def package_report(root: Path, package: str, directory: str, properties: str) -> PackageReport:
    metadata_hash: str | None = None
    properties_hash: str | None = None
    reports: list[LicenseReport] = []
    safe_refs: tuple[str, ...] = ()
    errors: list[str] = []
    try:
        value = bounded_read(root / directory / "package.xml", root, MAX_XML)
        metadata_hash = sha256(value)
        tree = parse_metadata(value)
        packages = [node for node in tree.iter() if local_name(node) == "localPackage"]
        if len(packages) != 1 or packages[0].get("path") != package:
            raise SDKPreflightError("installed_package_identity_mismatch")
        check_platform_api(package, packages[0])
        refs = [node.get("ref", "") for node in packages[0] if local_name(node) == "uses-license"]
        safe_refs = tuple(ref for ref in refs if LICENSE_ID.fullmatch(ref))
        if not refs or len(set(refs)) != len(refs):
            raise SDKPreflightError("missing_or_duplicate_license_refs")
        for identifier in refs:
            if LICENSE_ID.fullmatch(identifier) is None:
                raise SDKPreflightError("invalid_license_identifier")
            definitions = [
                node
                for node in tree.iter()
                if local_name(node) == "license" and node.get("id") == identifier
            ]
            if len(definitions) != 1:
                raise SDKPreflightError("missing_or_duplicate_license_text")
            definition = definitions[0]
            content = definition.text
            if len(definition) or content is None or not content.strip():
                raise SDKPreflightError("missing_or_mixed_license_text")
            if definition.get("type", "text") != "text":
                raise SDKPreflightError("unsupported_license_type")
            reports.append(license_report(root, identifier, content))
        data = bounded_read(root / directory / "source.properties", root, MAX_RECORD)
        properties_hash = sha256(data)
        if re.search(properties, data.decode("utf-8"), re.MULTILINE) is None:
            raise SDKPreflightError("installed_package_properties_mismatch")
    except UnicodeError:
        errors.append("properties_not_utf8")
    except SDKPreflightError as failure:
        errors.append(str(failure))
    if any(not report.accepted for report in reports):
        errors.append("license_acceptance_mismatch")
    return PackageReport(
        package,
        metadata_hash,
        properties_hash,
        safe_refs,
        tuple(reports),
        tuple(errors),
    )


def inspect_sdk(path: Path) -> SDKReport:
    root = path.resolve()
    packages = (
        package_report(
            root,
            "platforms;android-37.0",
            "platforms/android-37.0",
            r"^AndroidVersion\.ApiLevel\s*=\s*37\.0\s*$",
        ),
        package_report(
            root,
            "build-tools;36.0.0",
            "build-tools/36.0.0",
            r"^Pkg\.Revision\s*=\s*36\.0\.0\s*$",
        ),
    )
    errors: list[str] = []
    try:
        jar = root / "platforms/android-37.0/android.jar"
        if not jar.resolve().is_relative_to(root) or jar.stat().st_size == 0:
            raise SDKPreflightError("missing_or_empty_platform_jar")
        for tool in ("aapt2", "apksigner"):
            target = root / "build-tools/36.0.0" / tool
            if not target.resolve().is_relative_to(root) or not os.access(target, os.X_OK):
                raise SDKPreflightError("missing_or_nonexecutable_build_tool")
    except OSError:
        errors.append("missing_or_unreadable_platform_jar")
    except SDKPreflightError as failure:
        errors.append(str(failure))
    accepted = not errors and all(not report.errors and report.licenses for report in packages)
    return SDKReport(str(root), "android-37.0", "36.0.0", packages, accepted, tuple(errors))


def main() -> int:
    if len(sys.argv) != EXPECTED_ARGUMENTS or not sys.argv[1]:
        return 2
    report = inspect_sdk(Path(sys.argv[1]))
    sys.stdout.write(json.dumps(asdict(report), sort_keys=True) + "\n")
    return 0 if report.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
