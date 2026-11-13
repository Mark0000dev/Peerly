"""Closed metadata checks supplementing the existing PG/media acceptance baseline."""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path

from deployment.restore.accept_restore import RejectedError, inventory, load, unique
from deployment.restore.recovery_and import canonical_check

CATALOG_FORMAT = 3
MAX_IDENTIFIER = 63
MAX_DEFINITION_NAME = 4096
MAX_SEQUENCE_LINE = 2048
MAX_ENTRIES = 20000
MAX_SEQUENCES = 256
MAX_SEQUENCE_JSON = 256 * 2048
TARGET = re.compile(r"peerly_restore_[0-9a-f]{32}_test")
HEX = re.compile(r"[0-9a-f]{64}")
KINDS = frozenset(
    {
        "schema",
        "column",
        "relation",
        "constraint",
        "index",
        "trigger",
        "routine",
        "enum",
        "sequence",
    }
)


# Token boundaries are retained in the digest. Whitespace outside quoted tokens
# is immaterial; strings, identifiers, operators and casts are never discarded.
TOKENS = re.compile(
    r"[eE]'(?:[^'\\]|\\.|'')*'|'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"|"
    r"::|<=|>=|<>|!=|\|\||[A-Za-z_][A-Za-z0-9_$]*|[0-9]+|[^\s]"
)
MAX_DEFINITION = 65536


def definition_tokens(definition: str) -> list[str]:
    if len(definition.encode()) > MAX_DEFINITION:
        raise RejectedError("recovery_definition_bound")
    tokens = TOKENS.findall(definition)
    normalized: list[str] = []
    index = 0
    while index < len(tokens):
        match = literal_array(tokens, index)
        if match is None:
            normalized.append(tokens[index])
            index += 1
        else:
            index, replacement = match
            normalized.extend(replacement)
    return normalized


def legacy_definition_hash(definition: str) -> str:
    return hashlib.sha256(
        json.dumps(definition_tokens(definition), ensure_ascii=True).encode()
    ).hexdigest()


def definition_hash(definition: str) -> str:
    normalized = canonical_check(definition_tokens(definition))
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=True).encode()).hexdigest()


def literal_array(tokens: list[str], start: int) -> tuple[int, list[str]] | None:
    # PG16 deparse/reparse distributes ONLY this exact varchar-literal array cast.
    # No typmods, NULLs, functions, identifiers, arbitrary casts or expressions.
    if tokens[start : start + 3] != ["(", "ARRAY", "["]:
        return None
    index = start + 3
    result = ["ARRAY", "["]
    while index < len(tokens):
        literal = tokens[index]
        if not literal.startswith("'") or not literal.endswith("'"):
            return None
        if tokens[index + 1 : index + 4] != ["::", "character", "varying"]:
            return None
        result.extend(["(", literal, "::", "character", "varying", ")", "::", "text"])
        index += 4
        if tokens[index : index + 1] == [","]:
            result.append(",")
            index += 1
            continue
        if tokens[index : index + 6] != ["]", ")", "::", "text", "[", "]"]:
            return None
        result.append("]")
        return index + 6, result
    return None


def target_guard(source: str, target: str) -> None:
    if not source or source == target or TARGET.fullmatch(target) is None:
        raise RejectedError("recovery_database_identity")


def catalog(data: dict[str, object], heads: object) -> dict[tuple[str, str, str], str]:
    if (
        set(data) != {"format", "database", "heads", "entries", "invalid_indexes"}
        or type(data["format"]) is not int
        or data["format"] != CATALOG_FORMAT
        or data["heads"] != heads
        or type(data["invalid_indexes"]) is not int
        or data["invalid_indexes"] != 0
    ):
        raise RejectedError("recovery_catalog")
    values = data["entries"]
    if not isinstance(values, list) or not 0 < len(values) <= MAX_ENTRIES:
        raise RejectedError("recovery_catalog_bound")
    result: dict[tuple[str, str, str], str] = {}
    for value in values:
        if not isinstance(value, dict) or set(value) not in (
            {"kind", "schema", "name", "sha256"},
            {"kind", "schema", "name", "sha256", "definition"},
        ):
            raise RejectedError("recovery_entry")
        kind, schema, name, hashed = (value[k] for k in ("kind", "schema", "name", "sha256"))
        if (
            not isinstance(kind, str)
            or kind not in KINDS
            or not isinstance(schema, str)
            or not 0 < len(schema) <= MAX_IDENTIFIER
            or not isinstance(name, str)
            or len(name) > MAX_DEFINITION_NAME
            or not isinstance(hashed, str)
            or HEX.fullmatch(hashed) is None
        ):
            raise RejectedError("recovery_entry")
        key = (kind, schema, name)
        if key in result:
            raise RejectedError("recovery_duplicate")
        definition: object = value.get("definition")
        if definition is not None:
            if kind not in {"constraint", "index"} or not isinstance(definition, str):
                raise RejectedError("recovery_definition")
            if hashlib.sha256(definition.encode()).hexdigest() != hashed:
                raise RejectedError("recovery_definition_hash")
            hashed = definition_hash(definition)
        result[key] = hashed
    if ("schema", "public", "") not in result:
        raise RejectedError("recovery_public_schema")
    return result


def integer(value: object) -> int:
    if not isinstance(value, str) or re.fullmatch(r"-?[0-9]{1,20}", value) is None:
        raise RejectedError("sequence_integer")
    return int(value)


def sequences(raw: str, expected: set[tuple[str, str]]) -> int:
    if len(raw.encode()) > MAX_SEQUENCE_JSON or len(expected) > MAX_SEQUENCES:
        raise RejectedError("sequence_bound")
    seen: set[tuple[str, str]] = set()
    for line in raw.splitlines():
        if not line or len(line.encode()) > MAX_SEQUENCE_LINE:
            raise RejectedError("sequence_line")
        row: object = json.loads(line, object_pairs_hook=unique)
        if not isinstance(row, dict) or set(row) != {
            "schema",
            "name",
            "last",
            "called",
            "increment",
            "minimum",
            "maximum",
            "cycle",
            "owned",
            "edge",
        }:
            raise RejectedError("sequence_shape")
        schema, name = row["schema"], row["name"]
        if not isinstance(schema, str) or not isinstance(name, str):
            raise RejectedError("sequence_identity")
        key = (schema, name)
        if key not in expected or key in seen:
            raise RejectedError("sequence_set")
        seen.add(key)
        if type(row["called"]) is not bool or row["owned"] is not True or row["cycle"] is not False:
            raise RejectedError("sequence_requires_explicit_review")
        last, increment, minimum, maximum = (
            integer(row[k]) for k in ("last", "increment", "minimum", "maximum")
        )
        candidate = last + increment if row["called"] else last
        if increment == 0 or not minimum <= last <= maximum or not minimum <= candidate <= maximum:
            raise RejectedError("sequence_exhausted")
        if row["edge"] is not None:
            edge = integer(row["edge"])
            if (increment > 0 and candidate <= edge) or (increment < 0 and candidate >= edge):
                raise RejectedError("sequence_collision")
    if seen != expected:
        raise RejectedError("sequence_missing")
    return len(seen)


def verify(
    baseline: Path, source_catalog: Path, restored_catalog: Path, sequence_file: Path
) -> dict[str, object]:
    baseline_data = load(baseline)
    inventory(baseline_data)
    source, restored = load(source_catalog), load(restored_catalog)
    source_name, target_name = source.get("database"), restored.get("database")
    if not isinstance(source_name, str) or not isinstance(target_name, str):
        raise RejectedError("recovery_database_identity")
    target_guard(source_name, target_name)
    expected = catalog(source, baseline_data["heads"])
    actual = catalog(restored, baseline_data["heads"])
    if expected != actual:
        raise RejectedError("recovery_schema_mismatch")
    tables = baseline_data["tables"]
    if not isinstance(tables, dict) or any(
        ("relation", "public", name) not in expected for name in tables
    ):
        raise RejectedError("recovery_baseline_tables")
    descriptor = os.open(sequence_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "r") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SEQUENCE_JSON:
            raise RejectedError("sequence_file")
        raw = stream.read(MAX_SEQUENCE_JSON + 1)
    sequence_count = sequences(raw, {(s, n) for k, s, n in expected if k == "sequence"})
    return {
        "status": "catalog_match_sequences_safe",
        "catalog_entries": len(actual),
        "sequences_checked": sequence_count,
        "full_restore_proven": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("source_catalog", type=Path)
    parser.add_argument("restored_catalog", type=Path)
    parser.add_argument("sequences", type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.baseline, args.source_catalog, args.restored_catalog, args.sequences)
    except (RejectedError, OSError, ValueError):
        sys.stderr.write('{"event":"recovery_checks_failed"}\n')
        return 1
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
